# Phase 25: Smarter Memory - Context

**Gathered:** 2026-07-15
**Status:** Ready for planning

> **Session note:** The user launched `/gsd:discuss-phase 25`, was presented four
> phase-specific gray areas, **explicitly selected all four**, and **affirmatively chose the
> recommended option for each** (D-01…D-04) — not an AFK adoption. All numeric knobs (exact
> reinforcement window, the new kind's decay-days + salience weight) remain
> Claude's-/planner's-discretion per the standing Phase 11/13/14/15/16/17/21 precedent.
>
> This phase spends two long-deferred memory requirements: **MEM-06** was tracked as **MEM-F1**
> "salience reinforcement", **MEM-07** was tracked as **MEM-F2 / MEM-R2** "vision → RAG memory"
> (deferred out of v1.3 in the Phase 17 CONTEXT). Both are **additive** on the existing Phase
> 11/13 pgvector `user_memories` store — **no new table, no schema fork**, the kind-agnostic
> `MemoryService` design carries them exactly as it carried Phase 13's `taste_episode`.

<domain>
## Phase Boundary

Phase 25 makes Dexter's long-term memory **more durable and richer**, additively, on the existing
`user_memories` pgvector store:

- **MEM-06 (salience/durability reinforcement):** a memory that keeps proving relevant survives
  the daily decay sweep longer than an equally-old, never-surfaced memory. Reinforcement happens on
  the **read/recall path** (the moment a fact is surfaced), via **expiry extension only** (D-01).
- **MEM-07 (vision → RAG memory):** a successful vision roast persists **its own** distilled,
  number-free fact into `user_memories` under a **new dedicated memory kind** (D-04), gated by the
  same `is_sensitive` + `contains_number` accuracy/PII firewall every other kind goes through, and
  appearance-safe by distilling the **already-conduct-clamped roast line** (D-03).

**In scope:**
- MEM-06 — add expiry-extension reinforcement at the single `recall()` → `bump_surfaced`
  chokepoint (D-01/D-02); every recall surface reinforces uniformly.
- MEM-07 — a new `vision_roast`-style kind (short decay, low salience, guild-stamped), written
  fire-and-forget from `cogs/events.py::_maybe_fire_vision_roast` **only after a successful roast**
  (D-03/D-04), reusing the existing `distill_and_remember` orchestration unchanged.
- Additive config: one entry in `MEMORY_SALIENCE_BASE_WEIGHTS`, one in `MEMORY_DECAY_DAYS_BY_KIND`,
  and (if the planner chooses a fixed reinforcement window) at most one new reinforcement-window knob.
- **SC-3 byte-identical regression coverage** — the load-bearing guard that the new reinforcement
  and vision-kind paths do **not** perturb any pre-existing kind's salience baseline, decay, or
  dedup when those paths aren't exercised.

**Out of scope (belongs to later phases / future milestone):**
- Radio/endless mode, skip-voting, crossfade → Phases 26/27 (DJ-01/02/03).
- Portfolio finish → Phase 28.
- Reopening the Phase 21 **guild-scoping** read filter or the **write/dedup/eviction** path — the
  Phase 13 CR-01-scarred code stays untouched. MEM-06 touches the *surface-bookkeeping* (expiry)
  half of the read path, not the ANN-scoping half.
- Any new table, schema fork, new limiter, or a change to the kind-agnostic `MemoryService` API
  shape (SC-3).
- **Salience *bump* on recall** — deliberately rejected (D-01); reinforcement is expiry-only so
  intrinsic importance stays orthogonal to durability.
- A separate/neutral **second vision call** to describe the image — rejected (D-03) for cost +
  the conduct-clause duplication it would require.

</domain>

<decisions>
## Implementation Decisions

### MEM-06 — how surfacing reinforces durability

- **D-01 (user-selected): reinforce via EXPIRY EXTENSION ONLY; never mutate `salience` on the
  recall path.** The daily sweep (`database.delete_expired_memories`) deletes rows where
  `expires_at < now() AND salience < MEMORY_DECAY_SALIENCE_FLOOR (0.5)`. On surface, push the fact's
  `expires_at` further out so a frequently-recalled fact stays un-swept while an equally-old
  never-surfaced one expires and is evicted first (satisfies SC-1's "reinforced salience/**expiry**",
  the sweep evicts the unsurfaced one first). **Rationale for expiry-only over a salience bump:**
  keeps *importance* (salience — the ordinal ladder, `choose_eviction` ranking, the
  `MEMORY_SALIENCE_BASE_WEIGHTS` ladder) fully orthogonal to *durability* (recency of usefulness);
  it is naturally "use it or lose it" (stop surfacing → it ages out); and because `salience` — the
  field every other subsystem keys on — is never touched by recall, **SC-3 byte-identical is
  structurally easy to guarantee.** No immortality problem arises (a fact must be *continuously*
  re-surfaced to persist), so **no reinforcement ceiling is needed**.
  *(Rejected: **salience bump only** (like the existing dedup `bump_memory_hit` +0.02) — directly
  crosses the 0.5 sweep floor but lets a trivial `daily_batch` fact (0.2) recalled a few times become
  permanent AND outrank a real `milestone` for eviction protection, conflating importance with
  durability. Rejected: **both, salience capped below the floor** — belt-and-suspenders, more moving
  parts in the sweep for no gain over expiry-only.)*

- **D-02 (user-selected): every recall surface reinforces uniformly, at the single
  `recall()` → `database.bump_surfaced` chokepoint.** All recall surfaces (`/ask`, `/roast @user`,
  ambient roasts, proactive callbacks, the music-command memory callback, the auto-queue
  positive-taste blend) funnel through `MemoryService.recall()` step 7, which already calls
  `bump_surfaced` on the selected top-k facts. Reinforcement is one change **there** — no per-surface
  branching, no new param threaded through `recall()`. SC-1 is satisfied everywhere a memory proves
  useful.
  *(Rejected: **exclude `/ask` self-recall** — only count surfaces where "Dex chose to bring it up".
  Arguably purer, but it forces the chokepoint to learn which caller it's serving (a new param
  through `recall()`) for a distinction with no observed abuse/leak motive — `/ask` is self-scoped
  (MEM-02), so a user reinforcing their own recalled memory is harmless.)*

### MEM-07 — what a vision roast remembers, and how

- **D-03 (user-selected): distill the ROAST LINE Dex already generated — no second AI call — and
  rely on the Phase 17 conduct clause + the standard firewall for appearance safety.** The vision
  glue already produced a roast line that passed Phase 17's **"roast the content/vibe/subject, never
  a real person's face/body/weight/identity"** conduct clause (`build_vision_prompt`). Feeding that
  same line as `raw_text` into the existing `distill()` pipeline (a **text-only** distill — no image
  Part, no extra `gemini-2.5-flash` vision call) inherits that appearance discipline **and** runs the
  full `is_sensitive` + `contains_number` firewall. The stored memory reads as "the time they posted
  X and got clowned for Y" — a roast *episode*, appearance-safe by construction because its source
  was already appearance-clamped.
  *(Rejected: **a second neutral "describe the image" Gemini vision call** — a cleaner neutral fact,
  but burns another priority-2 vision call against the milestone's zero-new-cost theme AND would have
  to re-implement the appearance conduct clause for the description prompt, reopening the exact
  safety surface D-03 sidesteps.)*

- **D-04 (user-selected): a NEW dedicated short-decay, low-salience kind; write ONLY on a
  successful roast; guild-stamped.** Mirrors the Phase 13 `taste_episode` precedent exactly:
  - **New `kind`** (name is planner discretion — e.g. `vision_roast`), added as **one additive
    entry** to `config.MEMORY_SALIENCE_BASE_WEIGHTS` (a **low** base salience so image reactions are
    genuinely sweep-eligible and age out — likely `auto_queue_ignored`-tier, i.e. below the 0.5
    sweep floor) **and one** to `config.MEMORY_DECAY_DAYS_BY_KIND` (a **short** decay horizon, likely
    `taste_episode`-tier ~30d — images are ephemeral, shouldn't linger the default 90d).
  - **Fires only on the SUCCESS path** — a safety-blocked or otherwise skipped image (`line is None`
    in `_maybe_fire_vision_roast`) writes **nothing**. The memory write is gated behind the same
    rarity (chance `0.12` + per-user cooldown) as the roast itself, so the store isn't spammed.
  - **`guild_id`-stamped** (`str(message.guild.id)`), like every other unprompted write surface
    (Phase 21 MEM-03 discipline), so it participates correctly in guild-scoped recall.
  - **`exempt_numbers=False`** on the `distill()` call (the FULL number firewall applies — unlike
    `taste_episode`, a roast line has no legitimate artist-name digit justification).
  - Composes with **MEM-06**: a genuinely memorable image-moment that keeps getting recalled has its
    expiry reinforced (D-01) and survives; one-off reactions decay on the short horizon.
  *(Rejected: **standard 90-day / standard-salience treatment** — over-persists; a random meme
  reaction would linger as long as a milestone.)*

### Claude's / Planner's Discretion (do NOT re-ask the user)

- **The exact MEM-06 reinforcement-window mechanics (SQL shape).** Strong steer: **reuse/extend the
  existing D-05 self-refresh primitive `database.refresh_memory_expiry`** so a surfaced fact's
  `expires_at` resets to **its own kind's** horizon (`now() + resolve_decay_days(kind, ...)`),
  kind-aware — the same pattern already used by the write-path taste self-refresh.
  **Known wrinkle the researcher/planner MUST resolve:** `models.memory.MemoryFact` and
  `database.bump_surfaced` **do NOT currently carry `kind`** (`bump_surfaced` takes only `ids`), and
  `recall()`'s `MemoryFact` mapping drops the `kind` column that `search_memories` does return. So a
  kind-aware per-fact expiry reset needs `kind` threaded to the surface-bump path. A simpler
  acceptable alternative if kind-threading proves heavy: a **uniform fixed reinforcement window**
  (one new config knob, e.g. `MEMORY_SURFACE_REINFORCE_DAYS`) applied to all surfaced facts in one
  batch `UPDATE`. Planner picks; the researcher validates which cleanly satisfies SC-1 without
  perturbing SC-3.
- **Whether reinforcement is folded into the existing `bump_surfaced` UPDATE** (add an
  `expires_at = …` set-clause) **or a new sibling helper** — follow the `bump_surfaced` /
  `refresh_memory_expiry` idiom; keep it parameterized ($N), never string-interpolated.
- **The new vision kind's exact name + exact salience weight + exact decay-days** — numeric knobs,
  per the Phase 11/13 discretion-on-numbers precedent (salience **< 0.5** so it's sweep-eligible;
  decay short, ~`TASTE_DECAY_DAYS`).
- **Exact hook shape in `_maybe_fire_vision_roast`** — a fire-and-forget
  `asyncio.create_task` / `utils/tasks.py::make_task` spawning `distill_and_remember(...)` after the
  successful `message.reply`, mirroring the existing distill fire-and-forget sites in
  `cogs/music.py` / `cogs/ai.py` / `cogs/events.py`. Must never crash the roast path (the existing
  `distill_and_remember` already swallows all errors).
- **Exact SC-3 / SC-1 regression-test shape** — mock-free where the logic is pure (`models/memory.py`
  decay/eviction, any new pure helper); live-DB (CI's pgvector service container) for the
  surface→expiry-moved→sweep interaction and the vision-kind write-through-firewall path. Lock that a
  surfaced fact's `expires_at` moves while an unsurfaced equally-old one is swept first (SC-1), and
  that no pre-existing kind's salience/decay/dedup changes when the new paths are idle (SC-3).
- **Whether any new pure `logic/` seam is warranted** (e.g. a reinforcement-window computation) vs
  keeping it inline — likely a thin config lookup; planner decides, honoring the Phase 10 D-02 rule
  (glue dispatches on returned values, never mirrors branch logic).

### Reviewed Todos
None — `todo.match-phase 25` returned zero matches.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements (this phase)
- `.planning/ROADMAP.md` §"Phase 25: Smarter Memory" — goal + the 3 success criteria (SC-1
  reinforced expiry/eviction ordering, SC-2 vision fact through the firewall under its own kind,
  SC-3 additive/byte-identical).
- `.planning/REQUIREMENTS.md` §"Smarter Memory" — **MEM-06** and **MEM-07** verbatim; §"Future
  Requirements → Memory" (MEM-F3 the remaining deferred memory work — NOT this phase).
- `.planning/PROJECT.md` §"Key Decisions" — the kind-agnostic `MemoryService` invariant + the
  accuracy-firewall + rate-budget invariants this phase inherits; §"Current Milestone" MEM-06/07
  framing. The phase-close step adds the shipped reinforcement + vision-kind decisions here.

### The memory subsystem — READ BEFORE TOUCHING (the CR-01 / Phase 21 scar surface)
- `services/memory.py::recall` (`:60`) — the read half. **Step 7 (`:186`)** already calls
  `database.bump_surfaced([f.id for f in top])`; MEM-06's expiry extension lands **here / in that
  helper** (D-01/D-02). Note the `kind` column is fetched by `search_memories` but **dropped** in the
  `MemoryFact` mapping (`:147`–`:160`) — the kind-aware-expiry wrinkle.
- `services/memory.py::remember` (`:204`) + its **dedup branch (`:273`–`:301`)** — the write path
  and the **D-05 `expires_at` self-refresh** (gated on the MATCHED ROW's kind, CR-13-01). **MEM-06
  does NOT touch this** (D-01 is read-path expiry only); the D-05 pattern is the *primitive to
  reuse*, not the code to change.
- `services/memory.py::distill` (`:364`) + `distill_and_remember` (`:470`) — the kind-agnostic
  distill→remember orchestration MEM-07 reuses unchanged. Note `exempt_numbers` (`:391`) — vision
  passes **False** (full firewall). `distill_and_remember` swallows all errors (fire-and-forget safe).
- `services/memory.py::sweep` (`:522`) — the daily decay backstop; MEM-06 changes *which rows are
  still un-expired at sweep time*, not the sweep itself.
- `models/memory.py` — the pure scoring layer. **`MemoryFact`** dataclass (`:25`, has NO `kind`
  field), **`decay_predicate`** (`:435`, high-salience survives; MEM-06 works *with* it, not against),
  **`choose_eviction`** (`:232`, sorts by salience→created_at→hit_count — untouched by D-01 since
  salience isn't mutated), **`compute_salience`** (`:206`). Locked by `tests/test_memory.py`.
- `database.py` memory helpers: **`bump_surfaced`** (`:1734`, the MEM-06 hook — currently sets
  `last_surfaced_at=now()`, `surface_count+1`; takes only `ids`), **`refresh_memory_expiry`**
  (`:1553`, the expires_at-only UPDATE primitive to reuse), **`delete_expired_memories`** (`:1760`,
  the sweep — `expires_at < $1 AND salience < MEMORY_DECAY_SALIENCE_FLOOR`), **`insert_memory`**
  (`:1477`), **`bump_memory_hit`** (`:1528`, the +0.02 salience nudge — the *rejected* MEM-06
  approach's precedent), **`search_memories`** (`:1395`, returns `kind`).

### MEM-07 — the vision-roast hook + the conduct-clause source
- `cogs/events.py::_maybe_fire_vision_roast` (`:611`) — the hook point; add the memory write
  **after the successful `message.reply` (`:684`–`:694`)**, only when `line is not None`.
- `cogs/events.py::_generate_vision_roast` (`:561`) — produces the roast line MEM-07 distills;
  returns `str` on success, `None` on safety-block/empty (D-03 uses the `str` result as `raw_text`).
- `cogs/events.py::_first_valid_image_attachment` (`:43`) + `config.VISION_MIME_ALLOWLIST` — the
  pre-download structural gate already in place (no change).
- `personality/prompts.py::build_vision_prompt` — carries the Phase 17 **appearance conduct clause**
  that makes D-03's "distill the roast line" appearance-safe. (Read to confirm the clause is present;
  the memory fact's safety rests on it.)
- Existing fire-and-forget distill sites to mirror: `cogs/music.py` (`repeat_song`/`milestone`,
  guild-stamped), `cogs/ai.py` (`auto_queue_ignored`), `cogs/events.py` (ambient roast kinds) —
  all `distill_and_remember(..., guild_id=str(guild.id), ...)` via `create_task`/`make_task`.

### Config (additive entries only)
- `config.py:195` — `MEMORY_SALIENCE_BASE_WEIGHTS` (the ordinal ladder; MEM-07 adds one **low**
  entry, < 0.5 sweep floor like `taste_episode`=0.4 / `auto_queue_ignored`=0.4).
- `config.py:224` — `MEMORY_DECAY_DAYS_BY_KIND` (MEM-07 adds one **short**-horizon entry;
  `TASTE_DECAY_DAYS=30` is the sibling). `config.py:180` — `MEMORY_DECAY_SALIENCE_FLOOR=0.5`.
- `config.py:177` — `MEMORY_DECAY_DAYS=90` (the default horizon MEM-06 extends *from*/*to* per kind).
- `config.py:254`–`260` — `VISION_ROAST_CHANCE=0.12`, `VISION_ROAST_COOLDOWN_SECONDS=600`,
  `MAX_VISION_IMAGE_BYTES`, `VISION_MIME_ALLOWLIST` (the rarity gate the vision write inherits).
- `logic/taste.py::resolve_decay_days` — the kind→decay-days resolver (default + kind_overrides);
  the MEM-06 kind-aware expiry reset reuses this.

### CLAUDE.md invariants this phase must honor
- §"Critical Rules" 11–16 (memory rules) — esp. **12** (accuracy firewall: numbers from SQL, never
  embedded), **13** (never embed raw counts — applies to the vision fact too), **16** (`/memory
  forget` hard-deletes rows + embeddings — the new kind's rows are covered automatically since it's
  the same table). Rules **14/15** (vision safety-block = silent skip) are Phase 17's and stay intact.
- §"Implementation Gotchas → Phases 13–17" — the `taste_episode` **new-kind-not-new-table** pattern
  (MEM-07's template), the `MEMORY_DECAY_DAYS_BY_KIND` **new-mapping-not-mutation** discipline, and
  the D-05 self-refresh (`refresh_memory_expiry` is `expires_at`-only, never touches
  hit_count/salience/last_seen_at — MEM-06's expiry reuse follows the same restraint).
- §"Database Schema" — the running schema narrative; the new kind is documented as a `kind` value on
  `user_memories` (no DDL), same as `taste_episode` was.

### Prior-phase context (conventions inherited)
- `.planning/phases/17-vision-multimodal-roasting/17-CONTEXT.md` — the vision surface + the
  appearance conduct clause + the "vision→memory deferred (MEM-R2)" note this phase now spends;
  §"Out of scope" explicitly parked vision-memory needing "its own safety-gate design first" — D-03
  IS that design (distill the already-clamped line).
- `.planning/phases/21-memory-scoping-guild-data-lifecycle/21-CONTEXT.md` — the read-vs-write
  asymmetry, the guild-stamp-at-write discipline (the vision write follows it), and the CR-01 scar
  description; §"Deferred Ideas" lists **MEM-F1 salience reinforcement** (= MEM-06) as the deferred
  item this phase delivers.
- `.planning/phases/13-semantic-music-memory/*` (CONTEXT/RESEARCH) — the `taste_episode` new-kind +
  short-decay + below-floor-salience + D-05 self-refresh design MEM-07 and MEM-06 both mirror; the
  CR-01 cross-kind `expires_at` corruption the surface-expiry work must not reintroduce.

### Testing + CI
- `.planning/codebase/TESTING.md` — "pure logic gets mock-free TDD; Discord/process glue is
  untested-by-design (structural review + clean boot)."
- `tests/test_memory.py`, `tests/test_database_phase1*.py` — the regression surface: every test over
  `recall`/`search_memories`/`remember`/dedup/`expires_at`/`sweep`. The SC-3 byte-identical guard
  lives here.
- `tests/conftest.py` — `TEST_DATABASE_URL` + skip-on-connection-error; CI's `pgvector/pgvector:pg16`
  service container runs the live-DB reinforcement + vision-write tests.
- `.github/workflows/ci.yml` — the blocking Ruff + pytest gate.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `services/memory.py::recall` **step 7** / `database.bump_surfaced` — the single MEM-06 hook; every
  recall surface already funnels through it (D-02 needs no new surface plumbing).
- `database.refresh_memory_expiry` — the `expires_at`-only UPDATE primitive (D-05) MEM-06 reuses;
  its restraint (never touches salience/hit_count/last_seen_at) is exactly the D-01 discipline.
- `services/memory.py::distill_and_remember` — kind-agnostic distill→remember; MEM-07 calls it
  unchanged with the new kind + `exempt_numbers=False`, guild-stamped. Already fire-and-forget-safe.
- `config.MEMORY_SALIENCE_BASE_WEIGHTS` + `config.MEMORY_DECAY_DAYS_BY_KIND` + `resolve_decay_days` —
  additive one-line-each config entries register the new vision kind (the taste_episode template).
- `cogs/events.py::_maybe_fire_vision_roast` success tail — the write-hook site.

### Established Patterns
- **New memory kind = new `kind` value, never a new table** (Phase 13 `taste_episode`).
- **`MEMORY_DECAY_DAYS_BY_KIND` is a NEW mapping, extended additively** — kinds absent from it fall
  back to `MEMORY_DECAY_DAYS=90` byte-identically (the SC-3 guarantee for untouched kinds).
- **Read/write asymmetry** (Phase 21 D-02) — MEM-06 touches the *read/surface-bookkeeping* path
  (expiry), leaving the CR-01-scarred *write/dedup/eviction* path byte-identical.
- **Salience = intrinsic importance; expiry = durability** (D-01 keeps them orthogonal).
- **Guild-stamp every unprompted write** (Phase 21 MEM-03) — the vision write passes a real guild_id.
- **Accuracy firewall on every distilled fact** (`is_sensitive` + `contains_number`) — vision uses
  the full firewall (`exempt_numbers=False`).
- **Fire-and-forget, crash-proof memory writes** — `distill_and_remember` swallows all errors; the
  vision write must never crash `_maybe_fire_vision_roast`.

### Integration Points
- `database.bump_surfaced` (or a new sibling) — gains an `expires_at` reset; kind-aware via
  `resolve_decay_days` (needs `kind` threaded) OR a uniform fixed window (planner's call).
- `cogs/events.py::_maybe_fire_vision_roast` — spawns the fire-and-forget vision `distill_and_remember`
  after a successful send.
- `config.py` — two additive dict entries (+ optionally one reinforcement-window knob).
- **Regression surface:** every test over `recall`/`search_memories`/`remember`/dedup/`expires_at`/
  `sweep`, plus the new SC-1 (surface→expiry→sweep-ordering) and SC-2 (vision-write-through-firewall)
  live-DB tests.

</code_context>

<specifics>
## Specific Ideas

- **Reinforcement is "use it or lose it," not "recalled once = immortal."** Expiry-only (D-01) means
  a fact must be *continuously* re-surfaced to persist; the moment Dex stops finding it relevant, it
  resumes aging out. That is the whole point of picking expiry over a one-way salience ratchet — and
  it's why no ceiling is needed.
- **The vision memory is a roast *episode*, in Dex's voice, appearance-safe by construction.** Because
  the source text is the roast line that already obeyed the Phase 17 conduct clause, the stored fact
  can never be a body/appearance jab — the safety lives upstream in `build_vision_prompt`, not in a
  new gate. "the time they posted a blurry gym pic and got clowned for the lighting," never anything
  about the person.
- **Two features, one composition.** MEM-06 (durability) + MEM-07 (a new short-decay kind) meet at
  the sweep: a *memorable* image-moment that Dex keeps recalling has its expiry reinforced and
  survives; a forgettable one-off decays on the short horizon. Neither feature needs the other, but
  together they behave the way "smarter memory" should.
- **SC-3 is the whole risk.** The subsystem carried the Phase 13 CR-01 cross-kind `expires_at`
  corruption blocker and the Phase 21 guild-scoping surgery. The single most important review gate is
  proving no pre-existing kind's salience/decay/dedup shifts when the new paths are idle — which is
  exactly why D-01 chose expiry-only (salience, the field everything keys on, is never touched by
  recall).

</specifics>

<deferred>
## Deferred Ideas

- **Full guild-scoped `/ask` recall / per-user opt-in cross-guild memory sharing** → **MEM-F3**
  (Future Requirements) — untouched here; MEM-06/07 are orthogonal to scoping.
- **Salience *bump* on recall** (a one-way importance ratchet) → deliberately rejected (D-01);
  revisit only if expiry-only reinforcement proves insufficient in practice (not expected).
- **A second neutral "describe the image" vision call for a cleaner memory fact** → rejected (D-03)
  on cost + conduct-duplication; could be revisited if the roast-line-derived fact proves too terse.
- **A dedicated `/memory` surface for vision memories** (filtering `/memory view` by kind, etc.) →
  not needed — the new kind flows through the existing `/memory view` / `/memory forget` (RAG-04
  hard-delete covers it automatically since it's the same table). A kind filter is a later polish.

### Reviewed Todos (not folded)
None — `todo.match-phase 25` returned zero matches.

</deferred>

---

*Phase: 25-smarter-memory*
*Context gathered: 2026-07-15*
