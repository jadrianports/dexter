# Phase 25: Smarter Memory - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-15
**Phase:** 25-smarter-memory
**Areas discussed:** Reinforcement lever & ceiling (MEM-06), What a vision roast remembers (MEM-07), Vision memory's kind & lifespan (MEM-07), Which surfaces reinforce (MEM-06)

> All four gray areas were **explicitly selected** by the user, then each decision was the user's
> **affirmative choice of the recommended option** (not an AFK adoption). Numeric knobs left to
> planner discretion per the standing Phase 11–17/21 precedent.

---

## Reinforcement lever & ceiling (MEM-06)

| Option | Description | Selected |
|--------|-------------|----------|
| Extend expiry only | Each surface pushes expires_at out; salience never touched by recall — importance/durability orthogonal, ordinal ladder + eviction ranking pristine, SC-3 byte-identical, "use it or lose it", no ceiling needed | ✓ |
| Bump salience only | Nudge salience up each surface (like dedup +0.02); crosses the 0.5 sweep floor but a trivial daily_batch fact recalled a few times becomes permanent and outranks a milestone | |
| Both, salience capped below floor | Small nudge that can't cross 0.5 + expiry extension; belt-and-suspenders, more moving parts | |

**User's choice:** Extend expiry only (Recommended) → **D-01**
**Notes:** Chosen specifically because leaving `salience` untouched by the recall path makes the SC-3 byte-identical guarantee structural, and expiry-only is naturally "use it or lose it" so no immortality/ceiling problem arises.

---

## What a vision roast remembers (MEM-07)

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse the roast line | Distill the roast line Dex already generated — zero extra AI call; already passed Phase 17's content-not-appearance conduct clause, so appearance-safe by construction + the is_sensitive/number firewall | ✓ |
| Second "describe image" call | Neutral image description from a second priority-2 vision call; cleaner fact but burns budget + re-implements the conduct clause | |
| You decide | Take the recommended reuse-the-roast-line approach unless research says otherwise | |

**User's choice:** Reuse the roast line (Recommended) → **D-03**
**Notes:** Appearance safety rests upstream in `build_vision_prompt`'s conduct clause; distilling the already-clamped line inherits it. Stored as a roast *episode* ("posted X, got clowned for Y"), never an appearance jab.

---

## Vision memory's kind & lifespan (MEM-07)

| Option | Description | Selected |
|--------|-------------|----------|
| Short-decay ephemeral kind | New dedicated kind, short decay tier + low salience so image reactions age out (taste_episode pattern); fires only on a successful roast; guild-stamped | ✓ |
| Standard 90-day / standard salience | New kind but durable as any Phase 11 memory; over-persists ephemeral image reactions | |
| You decide | Take the recommended short-decay/low-salience/success-only/guild-stamped shape unless research says otherwise | |

**User's choice:** Short-decay ephemeral kind (Recommended) → **D-04**
**Notes:** Mirrors Phase 13 `taste_episode` exactly (new kind, one additive entry each in MEMORY_SALIENCE_BASE_WEIGHTS + MEMORY_DECAY_DAYS_BY_KIND). Composes with MEM-06: a memorable image-moment reinforced by recall survives; one-offs decay. `exempt_numbers=False` (full firewall).

---

## Which surfaces reinforce (MEM-06)

| Option | Description | Selected |
|--------|-------------|----------|
| Every surface, uniformly | One change at the bump_surfaced chokepoint; /ask, /roast, ambient, proactive, music callback, auto-queue taste blend all reinforce; SC-1 satisfied everywhere | ✓ |
| Exclude /ask self-recall | Only surfaces where "Dex chose to bring it up"; needs a new param through recall() | |
| You decide | Take the recommended uniform approach unless research surfaces a leak/abuse reason | |

**User's choice:** Every surface, uniformly (Recommended) → **D-02**
**Notes:** No per-surface branching. /ask is self-scoped (MEM-02), so a user reinforcing their own recalled memory is harmless — no motive to exclude it.

---

## Claude's Discretion

Recorded in CONTEXT.md §"Claude's / Planner's Discretion" — not surfaced as user questions (numeric/technical "how"):
- MEM-06 reinforcement-window SQL shape (reuse `refresh_memory_expiry` kind-aware vs a uniform fixed window; `MemoryFact`/`bump_surfaced` don't currently carry `kind`).
- The new vision kind's exact name + salience weight + decay-days (salience < 0.5, decay ~30d).
- The fire-and-forget hook shape in `_maybe_fire_vision_roast`.
- SC-1 / SC-3 regression-test shape (pure + live-DB pgvector container).

## Deferred Ideas

- Full guild-scoped `/ask` recall / cross-guild memory sharing → MEM-F3 (Future Requirements).
- Salience *bump* on recall → deliberately rejected (D-01).
- A second neutral "describe the image" vision call → rejected (D-03) on cost/conduct-duplication.
- A `/memory` kind-filter for vision memories → later polish (flows through existing view/forget).
