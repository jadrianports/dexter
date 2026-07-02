# Phase 14: Smarter Music Brain - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-02
**Phase:** 14-smarter-music-brain
**Areas discussed:** (all four presented; user stepped away before selecting — Claude decided on user's behalf)

---

> **Session note:** The user launched `/gsd:discuss-phase 14`, was presented the domain
> boundary and a four-option multiSelect of gray areas, then did not respond within the
> timeout. Following the Phase 13 precedent, Claude resolved all four areas using best
> judgment grounded in the BRAIN requirement text, Success Criterion 4 (multi-user-safety),
> and the Phase 11/13 accuracy-firewall precedent. The four areas below were the options
> presented; "Selected" reflects Claude's on-behalf decision, not a user click.

## Negative-hint shape (BRAIN-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Guild-collective skip aggregate | Number-free recently-skipped titles+artists injected as an "avoid these" prompt block; soft hint + light hard post-filter | ✓ |
| Per-active-listener skip lists | Skip lists scoped to who's in voice right now | (rejected — leak risk + fragility) |
| auto_queue_ignored memory only | Rely solely on the existing ignored-signal memory | (folded in as secondary, not primary) |

**Choice:** Guild-collective aggregate skip block (D-01) + defense-in-depth hard artist post-filter (D-02).
**Notes:** Auto-queue is already guild-scoped; Criterion 4 requires aggregate signals.

## Positive taste depth (BRAIN-01)

| Option | Description | Selected |
|--------|-------------|----------|
| In-room member taste blend | Recall taste_episode for each non-bot member in voice, blend as collective "the room likes…" positive context, capped | ✓ |
| Skip positive taste in auto-queue | Use only recent-plays + skip-negatives | (rejected — under-delivers BRAIN-01 "recent taste") |
| Single-invoker taste | Inject one user's taste into the shared queue | (rejected — no single invoker on the auto-queue trigger; leak risk) |

**Choice:** In-voice member taste blend, reusing the auto_queue_ignored member set (D-03).
**Notes:** Flagged OQ1 — recall() is currently kind-agnostic; needs a taste_episode filter.

## Discovery command UX (BRAIN-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Invoker-anchored + server co-occurrence, SQL-grounded, confirm-to-queue | Anchor on invoker's top artist; adjacency from guild-wide co-occurrence SQL; Gemini only voices it; offer to queue | ✓ |
| Gemini-generated recommendations | Let Gemini pick the adjacent artists | (rejected — violates zero-hallucination requirement) |
| Pure-info (no queue action) | Just print adjacency, no action | (folded — action is confirm-first, not silent) |

**Choice:** `/discover`, invoker-anchored, SQL-grounded adjacency, confirm-first queue (D-04/D-05).
**Notes:** Flagged OQ2 — co-occurrence SQL definition needs a concrete index-friendly shape.

## Jam assist surface (BRAIN-03)

| Option | Description | Selected |
|--------|-------------|----------|
| New `/jam suggest <name>`, validate, propose-and-confirm, append to snapshot | Sibling subcommand; validate via logic/autoqueue; confirm before writing | ✓ |
| Flag on `/jam add` | Overload the existing add subcommand | (rejected — muddier UX) |
| Silent auto-append | Add suggestions without confirmation | (rejected — mutates a shared server artifact silently) |

**Choice:** `/jam suggest` subcommand, validation-gated, propose-and-confirm, append to snapshot (D-06/D-07).
**Notes:** Reuses `validate_youtube_match` verbatim (BRAIN-03 hard requirement).

---

## Claude's Discretion

- All numeric priors (skip window ~7d/~15 rows, taste-fact cap ~3–4, discover adjacents 1–3,
  jam candidate count), exact new-helper SQL shapes, prompt-template edits, and `/discover`
  cog placement (`music.py` vs `ops.py`) — deferred to planning/spike + live tuning.

## Deferred Ideas

- Per-active-listener (non-aggregate) auto-queue personalization → revisit post-live if too bland.
- Embeddings-based track/artist similarity for discovery → future milestone (zero new infra now).
- `/roast`/`/ask`/`/memory` memory grounding → Phase 15. Proactive callbacks → Phase 16.
