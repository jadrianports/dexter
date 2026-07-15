# Phase 25: Smarter Memory - Research

**Researched:** 2026-07-15
**Domain:** Additive extension of an existing pgvector RAG memory subsystem (Python/asyncpg/Gemini) — no new library, no new infra.
**Confidence:** HIGH

## Summary

Phase 25 is pure surgery on `services/memory.py` + `database.py` + `models/memory.py` + `cogs/events.py` +
`config.py`. There is no new package, no new documentation to fetch, no Context7 lookup applicable — this
research is entirely codebase investigation, and every claim below is `[VERIFIED: <file>:<line>]` against
the live repo (read 2026-07-15), not training-data recall.

Both requirements are small, surgical, additive changes on a subsystem that already carries two prior scars
(Phase 13 CR-01 cross-kind `expires_at` corruption, Phase 21 guild-scoping surgery). The CONTEXT.md-flagged
"known wrinkle" (threading `kind` to the surface-bump path) turns out to be **cheap, not heavy** — but it
interacts with an existing test-fixture landmine that must be handled correctly or SC-3 (byte-identical
regression) breaks silently.

**Primary recommendation:**
- **MEM-06**: reinforce via a **new sibling DB helper** (`database.reinforce_memory_expiry`, mirroring
  `refresh_memory_expiry`'s expiry-only restraint but batched via `ANY($1)`), called from `recall()` step 7
  **grouped by kind**, using `resolve_decay_days()` per group (the existing D-05 idiom), with
  `SET expires_at = GREATEST(expires_at, $2)` as a safety net against ever *shortening* a fact's window.
  Thread `kind` as **service-local bookkeeping only** (a `dict[int, str | None]` built from the raw
  `search_memories` rows) — do **NOT** add a `kind` field to `models.memory.MemoryFact`. Map rows to
  `MemoryFact` using `row.get("kind")`-style access only where `kind` is actually read (i.e. nowhere in the
  dataclass mapping at all under this recommendation) so **zero bytes of `models/memory.py` change**.
- **MEM-07**: fire `memory_service.distill_and_remember(kind="vision_roast", exempt_numbers=False,
  guild_id=str(message.guild.id), base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS["vision_roast"])` via a
  bare `asyncio.create_task(...)` (matching the local `cogs/events.py` idiom, not `cogs/ai.py`'s
  `make_task`) immediately after the successful `message.reply(...)` in `_maybe_fire_vision_roast`, gated
  strictly on `line is not None`. Two additive config entries: `MEMORY_SALIENCE_BASE_WEIGHTS["vision_roast"]
  = 0.4` and `MEMORY_DECAY_DAYS_BY_KIND["vision_roast"] = TASTE_DECAY_DAYS` (reuse the existing constant, no
  new one).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| MEM-06 expiry reinforcement | API/Backend (`services/memory.py::recall` step 7) | Database (`database.py` new helper + `user_memories.expires_at`) | Recall is already the sole read-path chokepoint (D-02); reinforcement is a write-through-a-read side effect, same tier as the existing `bump_surfaced` call it sits beside. |
| MEM-06 decay-days resolution | API/Backend (`logic/taste.py::resolve_decay_days`, pure) | — | Already the established pure resolver reused by the D-05 write-path self-refresh; MEM-06 reuses it read-side. |
| MEM-07 vision fact distillation | API/Backend (`services/memory.py::distill`/`distill_and_remember`) | External API (Gemini `chat()` text-only call, priority=2) | Kind-agnostic orchestration MEM-07 calls unchanged; the Gemini call is the same text `chat()` path every other `distill_and_remember` caller uses — no new vision call. |
| MEM-07 hook / trigger | API/Backend glue (`cogs/events.py::_maybe_fire_vision_roast`) | Discord (message reply already sent) | The write is a fire-and-forget side effect of an already-completed Discord interaction, not a new user-facing surface. |
| MEM-07 storage | Database (`user_memories` table, existing schema, new `kind` value only) | — | No DDL — Phase 13 `taste_episode` precedent: new kind = new row value, never a new table/column. |
| Firewall / safety gate | API/Backend (`models/memory.py::is_sensitive`/`contains_number`, pure) | — | Both requirements route through the existing pure gate functions unchanged; this phase adds zero new gate logic. |

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01 (MEM-06)**: Reinforce via **EXPIRY EXTENSION ONLY**; never mutate `salience` on the recall path.
  Rationale: keeps intrinsic importance (salience) orthogonal to durability (expiry); "use it or lose it"
  (must be *continuously* re-surfaced to persist); `salience` — the field `choose_eviction`/sweep key on —
  is never touched by recall, making SC-3 structurally easy. No reinforcement ceiling needed.
- **D-02 (MEM-06)**: Every recall surface reinforces uniformly, at the single `recall()` → `bump_surfaced`
  chokepoint (step 7). No per-surface branching, no new param threaded through `recall()`. Includes `/ask`
  self-recall (rejected the "exclude /ask" alternative — no observed abuse motive, `/ask` is self-scoped).
- **D-03 (MEM-07)**: Distill the ROAST LINE Dex already generated — **no second AI call**. Feed the
  Phase-17-conduct-clamped roast line as `raw_text` into the existing text-only `distill()` pipeline
  (no image `Part`, no extra vision call). Appearance safety is inherited from `build_vision_prompt`'s
  conduct clause, not re-implemented.
- **D-04 (MEM-07)**: A NEW dedicated short-decay, low-salience kind (name is discretion, e.g.
  `vision_roast`); write ONLY on a successful roast (`line is not None`); `guild_id`-stamped;
  `exempt_numbers=False` (full firewall — unlike `taste_episode`, a roast line has no legitimate
  artist-name digit justification). Composes with MEM-06: a memorable image-moment that keeps getting
  recalled has its expiry reinforced and survives; one-off reactions decay on the short horizon.

### Claude's/Planner's Discretion

- Exact MEM-06 SQL shape (kind-aware vs. uniform-fixed-window) — **researcher validated below: kind-aware,
  via a new sibling helper, is cheap and correct; recommended.**
- Whether reinforcement folds into `bump_surfaced` or a new sibling helper — **researcher recommends a new
  sibling** (`reinforce_memory_expiry`), because a single `bump_surfaced` UPDATE cannot express a
  per-kind-group `expires_at` value in one statement without a `CASE`/`unnest` (more complex than the
  cap≤3 loop-of-groups alternative).
- New vision kind's exact name + salience weight + decay-days — **researcher recommends `vision_roast`,
  salience `0.4`, decay `TASTE_DECAY_DAYS` (30d)** — see MEM-07 section below.
- Exact hook shape in `_maybe_fire_vision_roast` — **researcher recommends bare `asyncio.create_task`**
  (matches the local file convention in `cogs/events.py`, not `cogs/ai.py`'s `make_task`) — see MEM-07
  section below.
- Exact SC-3/SC-1 regression-test shape — see Validation Architecture section below.
- Whether a new pure `logic/` seam is warranted — **researcher recommends NO new `logic/` file**; the only
  new "logic" is a config lookup (`resolve_decay_days`, already pure and already exists) plus a
  `dict`-grouping loop that is thin enough to stay inline in `services/memory.py` (D-02: glue dispatches on
  returned values, never mirrors branch logic — there is no branch logic here to extract, just a groupby).

### Deferred Ideas (OUT OF SCOPE)

- MEM-F3 (full guild-scoped `/ask` recall / cross-guild sharing) — untouched, orthogonal.
- Salience *bump* on recall (one-way importance ratchet) — rejected (D-01).
- A second neutral "describe the image" vision call — rejected (D-03), cost + conduct-duplication.
- A dedicated `/memory` filter-by-kind surface — not needed, existing `/memory view`/`forget` cover it.
- Reopening the Phase 21 guild-scoping read filter or the Phase 13 CR-01-scarred write/dedup/eviction path.
- Any new table, schema fork, new limiter, or change to the kind-agnostic `MemoryService` API shape.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MEM-06 | Memories that get surfaced/hit gain durability — a surfaced memory's expiry is reinforced so frequently-relevant facts outlive one-off ones under the daily decay sweep. | Resolved: `database.reinforce_memory_expiry` (new) + kind-grouped call from `recall()` step 7 (§ Standard Stack / Code Examples / Architecture Patterns). Confirmed only sweep-eligible kinds (salience < 0.5) are practically affected — see Pitfall 1. |
| MEM-07 | A vision roast persists a distilled, number-free fact into long-term memory, subject to the same sensitivity/accuracy firewall as every other kind. | Resolved: new `vision_roast` kind + fire-and-forget `distill_and_remember(...)` call from `_maybe_fire_vision_roast` after successful send (§ Code Examples). Firewall/salience/decay wiring specified in § Standard Stack. |
</phase_requirements>

## Standard Stack

No new library, framework, or service is introduced by this phase. Everything below is existing project
infrastructure being extended additively.

### Core (existing, reused unchanged)
| Component | Location | Purpose | Why reused as-is |
|-----------|----------|---------|-------------------|
| `MemoryService.recall/remember/distill/distill_and_remember/sweep` | `services/memory.py` | Kind-agnostic RAG lifecycle | Both MEM-06 and MEM-07 are explicitly required to stay additive to this API shape (SC-3). |
| `resolve_decay_days(kind, default_days, kind_overrides)` | `logic/taste.py:186` | Pure kind→decay-days resolver | Already used by the D-05 write-path self-refresh; MEM-06 reuses it read-side, MEM-07 reuses it write-side (already wired into `remember()`, needs zero change for MEM-07). |
| `database.refresh_memory_expiry` | `database.py:1553` | The `expires_at`-only UPDATE **idiom** (single id) | Template for the new MEM-06 helper — same restraint (never touches `hit_count`/`salience`/`last_seen_at`), extended to batch via `ANY($1)`. |
| `database.bump_surfaced` | `database.py:1734` | `last_surfaced_at`/`surface_count` bump (batched `ANY($1)`) | **Stays completely untouched** — MEM-06 adds a sibling call beside it in `recall()` step 7, never modifies its SQL or signature (this is what keeps it byte-identical for SC-3). |
| `is_sensitive` / `contains_number` | `models/memory.py:362,404` | Pure PII/accuracy firewall | MEM-07 routes through these unchanged via `distill(exempt_numbers=False)`. |
| `config.MEMORY_SALIENCE_BASE_WEIGHTS` / `MEMORY_DECAY_DAYS_BY_KIND` | `config.py:195,224` | Ordinal salience ladder / per-kind decay override | MEM-07 adds one entry to each (additive dict literals — the established Phase-13 `taste_episode` pattern). |

### New (additive-only)
| Item | Location | Purpose | Why standard |
|------|----------|---------|--------------|
| `database.reinforce_memory_expiry(pool, ids: list[int], expires_at: datetime) -> None` | new, sibling to `refresh_memory_expiry` in `database.py` | Batch expiry-only UPDATE for MEM-06 | Follows the exact idiom already established (`refresh_memory_expiry`/`bump_surfaced`): parameterized `$N`, `ANY($1)` array binding, expiry-only restraint. |
| `config.MEMORY_SALIENCE_BASE_WEIGHTS["vision_roast"] = 0.4` | `config.py` (append to existing dict) | New kind's base salience | Matches `auto_queue_ignored`/`taste_episode` precedent — below `MEMORY_DECAY_SALIENCE_FLOOR` (0.5) so it is genuinely sweep-eligible. |
| `config.MEMORY_DECAY_DAYS_BY_KIND["vision_roast"] = TASTE_DECAY_DAYS` | `config.py` (append to existing dict) | New kind's decay horizon | Reuses the existing `TASTE_DECAY_DAYS = 30` constant (`config.py:208`) rather than a new literal — one less magic number, same "images are ephemeral" rationale CONTEXT.md gives for `taste_episode`. |

### Alternatives Considered
| Instead of | Could use | Tradeoff |
|------------|-----------|----------|
| Kind-aware reinforcement (new sibling helper, grouped calls) | Uniform fixed-window reinforcement (one new `MEMORY_SURFACE_REINFORCE_DAYS` knob, single batch UPDATE folded into `bump_surfaced`) | Simpler (one UPDATE, no grouping, no new helper) but has a real correctness bug unless guarded: a uniform window shorter than a kind's *own* decay horizon would **shorten** that kind's remaining life on reinforcement (e.g. `daily_batch` default 90d reinforced to a 30d uniform window at day 5 = net *shortening*, not reinforcement). Fixable with `GREATEST(expires_at, $2)`, but at that point the kind-aware version costs barely more and is strictly more correct. **Not recommended as primary, documented as fallback if grouping proves awkward at plan time.** |
| New sibling DB helper | Fold into `bump_surfaced` (add `expires_at = $N` SET clause, single shared value) | Only works for the uniform-window alternative above (one value for all ids in one call); cannot express per-kind-group values in a single UPDATE without `CASE WHEN kind = ... THEN ...` (adds real complexity for zero benefit given the cap≤3 loop is already cheap). |
| `vision_roast` kind name | `image_reaction`, `vision_memory` | Any name works; `vision_roast` most directly names the Phase-17 surface it originates from and reads naturally next to `taste_episode`/`repeat_song` in logs. Purely stylistic — planner's call. |

**Installation:** None. No `pip install` / `requirements.txt` change. Zero new packages.

**Version verification:** N/A — no new package.

## Package Legitimacy Audit

**Not applicable.** This phase installs zero external packages. No `pip install`, no new `requirements.txt`
entry, no new import outside the existing project tree. The Package Legitimacy Gate protocol is skipped by
its own trigger condition ("every phase that installs external packages").

## Architecture Patterns

### System Architecture Diagram

```
MEM-06 (reinforcement) — read-path side effect
─────────────────────────────────────────────────────────────────────────
  /ask, /roast, ambient roast, proactive callback,           (any recall()
  auto-queue taste blend, music-command callback  ──────┐     call site,
                                                         │     unchanged)
                                                         ▼
                                      MemoryService.recall()
                                      ┌─────────────────────────────────┐
                                      │ 1. embed query (unchanged)      │
                                      │ 2. search_memories (unchanged,  │
                                      │    already returns `kind`)      │
                                      │ 3. map rows -> MemoryFact       │
                                      │    (unchanged — NO kind field)  │
                                      │ 4. apply_floor (unchanged)      │
                                      │ 5. rerank (unchanged)           │
                                      │ 6. cap to MEMORY_INJECT_CAP     │
                                      │ 7a. bump_surfaced(ids)  <- SAME │
                                      │     call, byte-identical        │
                                      │ 7b. NEW: group top by kind      │
                                      │     (local dict built from raw │
                                      │     `rows`, not MemoryFact) ->  │
                                      │     reinforce_memory_expiry()  │
                                      │     once per distinct group     │
                                      └─────────────────────────────────┘
                                                         │
                                                         ▼
                                      database.reinforce_memory_expiry
                                      UPDATE user_memories
                                      SET expires_at = GREATEST(expires_at, $2)
                                      WHERE id = ANY($1)
                                                         │
                                                         ▼
                                      user_memories.expires_at pushed out
                                      (only meaningfully affects rows with
                                      salience < 0.5 — see Pitfall 1)
                                                         │
                                                         ▼
                                      MemoryService.sweep() (unchanged
                                      SQL) evicts unreinforced rows first


MEM-07 (vision memory write) — fire-and-forget side effect of a successful roast
─────────────────────────────────────────────────────────────────────────
  Image posted in ambient channel
        │
        ▼
  _maybe_fire_vision_roast (cogs/events.py:611)
        │  1. structural mime/size gate
        │  2. opt-out check
        │  3. cadence gate (chance + cooldown)
        │  4. read bytes -> _generate_vision_roast()
        │       -> Gemini vision chat() (existing, unchanged)
        │       -> str (success) | None (safety-block/empty)
        │  5. re-check ambient-channel silence (TOCTOU guard)
        │  6. message.reply(line)  <- existing, unchanged
        │
        ▼  (only reached when the reply SUCCEEDS and line is not None)
  NEW: asyncio.create_task(
         memory_service.distill_and_remember(
           user_id=str(message.author.id),
           guild_id=str(message.guild.id),
           raw_text=line,              # the roast line, NOT the image
           kind="vision_roast",
           base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS["vision_roast"],
         )
       )
        │
        ▼
  distill_and_remember (unchanged orchestration)
        │  1. distill(line, exempt_numbers=False)   <- text-only Gemini call,
        │     priority=2, is_sensitive + contains_number firewall applies
        │  2. compute_salience(base_salience)         (unchanged)
        │  3. remember(..., kind="vision_roast", ...)  (unchanged; inserts with
        │     expires_at = now + resolve_decay_days("vision_roast", ...))
        ▼
  user_memories row, kind='vision_roast', salience 0.4, decay 30d
  (now eligible for MEM-06 reinforcement on future recall)
```

### Recommended Project Structure

No new files. Changes land in existing files only:

```
database.py          # + reinforce_memory_expiry (new sibling helper, near refresh_memory_expiry:1553)
services/memory.py   # recall() step 7 extended with kind-grouped reinforcement call
config.py            # + 2 dict entries (MEMORY_SALIENCE_BASE_WEIGHTS, MEMORY_DECAY_DAYS_BY_KIND)
cogs/events.py        # _maybe_fire_vision_roast: + fire-and-forget distill_and_remember call
tests/test_memory.py            # + pure/mocked tests for the grouping logic + MEM-06 recall regression
tests/test_database_phase25.py  # NEW — live-DB tests (SC-1 surface->expiry->sweep, SC-2 vision write)
```

### Pattern 1: Kind-Grouped Batch Reinforcement (MEM-06)

**What:** After `recall()` selects its top-k facts (≤ `MEMORY_INJECT_CAP` = 3), group their ids by
resolved decay-days (via `resolve_decay_days(kind, ...)`), then call `reinforce_memory_expiry` once per
distinct group. With a cap of 3, this is at most 3 tiny grouped UPDATEs — negligible added latency on a
call path that already does an embed round-trip + an ANN query.

**When to use:** Exactly this one call site (`recall()` step 7). No other surface should call it directly —
D-02 keeps reinforcement centralized at the single chokepoint.

**Example (recommended implementation shape):**
```python
# Source: pattern derived from services/memory.py:60-198 (recall) + database.py:1553 (refresh_memory_expiry idiom)

# services/memory.py — inside MemoryService.recall(), replacing step 7:

# Step 7a — bump last_surfaced_at / surface_count (UNCHANGED — byte-identical call,
# same function, same args, so every existing mock of database.bump_surfaced still works).
await database.bump_surfaced(self._pool, [f.id for f in top])

# Step 7b — MEM-06: reinforce expiry, grouped by each fact's own kind (D-01/D-02).
# `kind` is read from the RAW rows (not MemoryFact — the dataclass is never touched),
# via a small id -> kind lookup built alongside the existing MemoryFact mapping.
kind_by_id = {row["id"]: row.get("kind") for row in rows}
now2 = datetime.now(timezone.utc)
groups: dict[int, list[int]] = {}  # decay_days -> [ids]
for f in top:
    days = resolve_decay_days(
        kind_by_id.get(f.id),
        default_days=config.MEMORY_DECAY_DAYS,
        kind_overrides=config.MEMORY_DECAY_DAYS_BY_KIND,
    )
    groups.setdefault(days, []).append(f.id)
for days, ids in groups.items():
    await database.reinforce_memory_expiry(
        self._pool, ids, now2 + timedelta(days=days)
    )
```
```python
# Source: pattern derived from database.py:1553-1576 (refresh_memory_expiry, the sibling to extend)

async def reinforce_memory_expiry(pool: asyncpg.Pool, ids: list[int], expires_at: datetime) -> None:
    """Push out expires_at for a batch of surfaced facts sharing one resolved decay
    horizon (MEM-06 / D-01). Sibling to refresh_memory_expiry (same expiry-only
    restraint — never touches hit_count/salience/last_seen_at) but batches over
    multiple ids in one UPDATE via ANY($1), mirroring bump_surfaced's array-binding
    shape. GREATEST(...) guarantees reinforcement can only extend, never shorten,
    a fact's remaining window — defends against a reinforcement call landing with
    a shorter target date than the fact's current expires_at (e.g. a stale group
    computation or a future non-uniform caller).
    """
    if not ids:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE user_memories SET expires_at = GREATEST(expires_at, $2) WHERE id = ANY($1)",
            ids,
            expires_at,
        )
```

**Why `row.get("kind")` and not `row["kind"]`:** `search_memories` (`database.py:1465`) already selects
`kind` in every row, so on a real asyncpg.Record this is never `None`-by-missing-key. But the existing
hand-rolled test fixtures in `tests/test_memory.py` (`TestRecallService`, `TestRecallKindParam`,
`TestRecallGuildScoped`) construct rows as plain dicts wrapped in `_DictRecord(dict)`
(`tests/test_memory.py:1816`) **without a `"kind"` key** — e.g. `below_floor_rows`/`above_floor_rows` at
`tests/test_memory.py:457-469,501-513`. `_DictRecord.__getitem__` is a straight `dict.__getitem__`
override, so `row["kind"]` on these fixtures raises `KeyError` immediately — but `dict.get()` is inherited
unmodified (Python's C-level `dict.get` does not go through the overridden `__getitem__`), verified live:
`asyncpg.Record` also exposes `.get()` (confirmed via `'get' in dir(asyncpg.Record)` on the installed
`asyncpg==0.31.0`). Using `.get("kind")` everywhere `kind` is read from a raw row is therefore the ONLY
form that is simultaneously (a) correct against real DB rows and (b) silently backward-compatible with
every existing test fixture that predates this phase — this is the concrete resolution of the CONTEXT.md
"known wrinkle."

### Pattern 2: Fire-and-Forget Post-Success Memory Write (MEM-07)

**What:** Mirror the four existing `distill_and_remember` fire-and-forget call sites exactly
(`cogs/music.py:1330-1338,1360-1368,1400-1408`, `cogs/events.py:284-292`, `cogs/ai.py:515-525`) — same
signature shape (`user_id=`, `guild_id=`, `raw_text=`, `kind=`, `base_salience=`), same "only after a
successful, already-completed user-facing action" placement.

**When to use:** Exactly `_maybe_fire_vision_roast`, after the `try/except discord.HTTPException` block
around `message.reply(...)` succeeds (i.e. AFTER line 688 `mention_author=False,)` closes, BEFORE or AFTER
the cooldown-mark line — ordering between the memory-write task spawn and the cooldown mark does not matter
since both are independent side effects of the same successful send.

**Example:**
```python
# Source: pattern derived from cogs/events.py:683-694 (existing successful-send site) +
# cogs/events.py:284-292 (existing local fire-and-forget idiom — bare create_task, no make_task)

try:
    await message.reply(
        line,
        allowed_mentions=discord.AllowedMentions.none(),
        mention_author=False,
    )
except discord.HTTPException:
    # Send failed — do not mark the cooldown (allow a future retry).
    return

# Successful send — mark the per-user cooldown.
self._vision_roast_cooldowns[message.author.id] = asyncio.get_event_loop().time()

# MEM-07: fire-and-forget vision memory write — ONLY reached when line is not None
# AND the send succeeded. distill_and_remember already swallows all internal errors
# (Gemini transport failure, firewall rejection, DB write failure), so this can never
# crash the roast path even if awaited synchronously — but it is fire-and-forget
# (create_task) to match every other distill_and_remember call site and avoid adding
# latency to the (already-completed) user-visible interaction.
memory_service = getattr(self.bot, "memory_service", None)
if memory_service is not None:
    asyncio.create_task(
        memory_service.distill_and_remember(
            user_id=str(message.author.id),
            guild_id=str(message.guild.id),
            raw_text=line,
            kind="vision_roast",
            base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS["vision_roast"],
        )
    )
```

**Why bare `create_task` and not `make_task`:** `cogs/events.py` already uses bare `asyncio.create_task`
for its one existing `distill_and_remember` call (line 284) — mirroring the *local file's own* convention
is more consistent than importing `make_task` (used by `cogs/ai.py`, a different cog) into a file that has
never used it. Both are fire-and-forget-safe since `distill_and_remember` never raises; `make_task`'s only
added value (surfacing exceptions, named task) is not load-bearing here given the swallow-everything
contract already documented at `services/memory.py:513-516`. Planner may choose `make_task` instead for
stronger observability — either is behaviorally safe; note this is Claude's/planner's discretion, not a
locked decision.

### Anti-Patterns to Avoid

- **Do NOT add a `kind` field to `models.memory.MemoryFact`.** It is not needed (Pattern 1 above threads
  kind via a service-local dict built from the raw `rows`, never via the dataclass), and adding it touches
  the most scar-laden pure file in the subsystem (locked by ~80 tests) for zero behavioral gain.
- **Do NOT modify `database.bump_surfaced`'s SQL or signature.** Every existing recall-path test that
  monkeypatches it does so with the current `(pool, ids)` shape; changing it risks a silent behavioral
  drift that SC-3 exists to catch. Add a sibling instead.
- **Do NOT compute `expires_at` inside SQL (`now() + interval '30 days'`).** Every existing expiry-setting
  helper (`insert_memory`, `refresh_memory_expiry`) computes the datetime in Python and passes it as a
  parameter — this is the established idiom (keeps the decay-days constant visible/testable in Python, not
  buried in a SQL string) and must be followed for `reinforce_memory_expiry` too.
- **Do NOT call `distill()` with `exempt_numbers=True` for `vision_roast`.** Unlike `taste_episode` (whose
  raw text is a fixed number-free template where any digit is provably an artist name — WR-13-02), a vision
  roast line is free-form Gemini output about an arbitrary image; it has no equivalent digit-provenance
  guarantee, so the full firewall must apply (D-04 explicit).
- **Do NOT fire the memory write before the `message.reply` succeeds**, and do NOT fire it when
  `line is None` (safety-block/empty). A pre-send or unconditional write would (a) persist content the user
  never actually saw sent, and (b) violate D-04's "write ONLY on a successful roast."

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Kind → decay-days resolution | A second lookup/if-chain in `services/memory.py` | `logic.taste.resolve_decay_days` (already exists, pure, tested) | Already the single source of truth the D-05 write-path self-refresh uses; a second implementation would be a divergence risk (two places that must agree on "what decay-days does kind X get"). |
| Salience computation for the new kind | A bespoke vision-specific salience formula | `models.memory.compute_salience(base_weight)` via `distill_and_remember`'s existing call | Kind-agnostic by design (D-07 hybrid salience) — `vision_roast` is just another entry in `MEMORY_SALIENCE_BASE_WEIGHTS`, exactly like `taste_episode` was. |
| Accuracy/PII firewall for the vision fact | A second sensitivity/number regex pass specific to vision | `models.memory.is_sensitive` / `contains_number` via `distill()`'s existing backstop | These are already the deterministic backstop behind the DISTILL_PROMPT LLM gate; a parallel implementation would need to be kept in sync forever for no benefit. |
| Fire-and-forget task management | A new async task wrapper for the vision-memory write | `asyncio.create_task` (local convention) or `utils/tasks.py::make_task` | Both already exist and are proven; a third pattern adds cognitive overhead with zero new capability. |

**Key insight:** Every piece MEM-06/MEM-07 need already exists in this codebase in a form built for exactly
this kind of additive extension (the Phase 13 `taste_episode` precedent is the literal template for MEM-07;
the Phase 11 D-05 self-refresh is the literal template for MEM-06). The entire research finding is: **do not
build anything new except one DB helper and two config entries — everything else is composition.**

## Runtime State Inventory

Not applicable — this is a greenfield-within-existing-schema additive phase, not a rename/refactor/migration.
No stored data changes meaning, no live-service config outside git, no OS-registered state, no secret/env
var renames, no build-artifact staleness. `MEMORY_DECAY_DAYS_BY_KIND`/`MEMORY_SALIENCE_BASE_WEIGHTS` gain
new dict entries (code change only, no data migration — existing rows of other kinds are untouched, new
`vision_roast` rows simply don't exist until the first vision roast fires post-deploy).

## Common Pitfalls

### Pitfall 1: Reinforcement is a no-op for high-salience kinds (by design, but must be understood)

**What goes wrong:** A planner or reviewer might expect MEM-06 to visibly change `milestone`/`late_night`/
`repeat_song` fact lifetimes and be confused when it doesn't.

**Why it happens:** `database.delete_expired_memories` (`database.py:1760`) only sweeps rows where
`salience < config.MEMORY_DECAY_SALIENCE_FLOOR` (0.5) **AND** `expires_at < now()`. Current salience
weights (`config.py:195-203`): `milestone=1.0`, `late_night=0.7`, `repeat_song=0.5`, `auto_queue_ignored=0.4`,
`daily_batch=0.2`, `taste_episode=0.4`. Only `auto_queue_ignored`, `daily_batch`, `taste_episode` (and the
new `vision_roast=0.4`) ever satisfy `salience < 0.5` — `repeat_song`'s `0.5` is NOT `< 0.5`, so it too is
permanently retained regardless of `expires_at`. Pushing `expires_at` further out for a `milestone` fact is
therefore harmless but **functionally invisible** — it was never going to be swept anyway.

**How to avoid:** This is expected, correct behavior, not a bug — SC-1's "an equally-old, never-surfaced
memory" example is meaningful precisely for the low-salience kinds (`daily_batch`, `auto_queue_ignored`,
`taste_episode`, `vision_roast`). The live-DB SC-1 test (see Validation Architecture) MUST use a
sweep-eligible kind (salience < 0.5) as its fixture, or the test will pass vacuously without exercising the
real reinforcement-vs-sweep interaction.

**Warning signs:** A live-DB test that inserts two `milestone` facts (one surfaced, one not) and asserts
"the surfaced one survives the sweep, the other doesn't" would be **vacuously true for the wrong reason**
(neither would ever be swept) — this exact anti-pattern must be avoided when the planner writes the SC-1
acceptance test.

### Pitfall 2: New DB call in `recall()` step 7 breaks existing `TestRecallService` mocks unless updated

**What goes wrong:** `tests/test_memory.py::TestRecallService::test_returns_capped_facts_when_some_clear_floor`
(`tests/test_memory.py:489`) is the **only** existing unit test whose `above_floor` result is non-empty and
therefore actually reaches step 7's `bump_surfaced` call in the real code path (verified: every other
`TestRecallService`/`TestRecallKindParam`/`TestRecallGuildScoped` test either raises before reaching search,
or has its `fake_search` stub return `[]`, which short-circuits at the floor check before step 7). That one
test monkeypatches `database.search_memories` and `database.bump_surfaced` but **not** any new function —
adding an unconditional second DB call (`database.reinforce_memory_expiry`) inside step 7 will make this
test attempt a real DB call against a `MagicMock()` pool, which will raise (no `__aenter__`/`__aexit__`
support on a plain `MagicMock`), failing the test.

**Why it happens:** The existing pattern is "every function `recall()` calls must be monkeypatched by name
in every test that exercises the code path reaching it" — this is not automatic/inherited, it's manual per
test.

**How to avoid:** The plan MUST include a task step that adds
`database.reinforce_memory_expiry = fake_reinforce` (no-op stub, following the exact `fake_bump` pattern
already at `tests/test_memory.py:474-475,521-522`) to `test_returns_capped_facts_when_some_clear_floor`'s
try/finally monkeypatch block. This is a small, precisely-scoped, one-test change — not a wide regression,
but it WILL fail CI if skipped.

**Warning signs:** `pytest tests/test_memory.py -k test_returns_capped_facts_when_some_clear_floor` failing
with an `AttributeError`/`TypeError` about `__aenter__` or similar on a `MagicMock` after the MEM-06 change
lands, but before the test's monkeypatch list is updated.

### Pitfall 3: `refresh_memory_expiry`'s single-id shape is NOT what MEM-06 should extend

**What goes wrong:** A tempting shortcut is "just call the existing `refresh_memory_expiry` in a loop, once
per surfaced fact" instead of writing a new batched helper.

**Why it happens:** It requires zero new SQL.

**How to avoid:** This works functionally (≤3 round trips either way, since `MEMORY_INJECT_CAP=3`), but
diverges from the established "batch via `ANY($1)`" idiom used by `bump_surfaced` for exactly this same
kind of "act on the top-k selected ids" operation, and it does not naturally support the `GREATEST(...)`
safety net without also reading the existing `expires_at` first (extra round trip) or duplicating the
`GREATEST` clause into `refresh_memory_expiry` itself (which would change behavior for the D-05 dedup
self-refresh call site — an actual SC-3 risk, since `refresh_memory_expiry` is currently a hard overwrite,
not a `GREATEST`). **Recommendation stands: new sibling helper, not a loop over the existing single-id one.**

### Pitfall 4: `vision_roast`'s `raw_text` is the roast LINE, not the image description

**What goes wrong:** Confusing "distill the image" with "distill the roast line Dex already said."

**Why it happens:** MEM-07 sounds like "remember what was in the picture," but D-03 explicitly rejected a
second vision call.

**How to avoid:** `raw_text=line` where `line` is `_generate_vision_roast`'s return value (the text Dex
actually sent to the channel), not the image bytes or any image metadata. This is why the write must happen
strictly after `_generate_vision_roast` returns a non-`None` string AND the reply send succeeds.

**Warning signs:** A test that asserts the stored fact references pixel/visual details the roast line itself
doesn't mention would indicate a wrong implementation (a second vision call snuck in).

## Code Examples

See "Architecture Patterns" § Pattern 1 and Pattern 2 above for the two verified, ready-to-implement code
shapes (both derived directly from existing in-repo idioms, not external documentation — there is no
external library surface in this phase).

## State of the Art

Not applicable — no external library/framework version drift to track. This phase's "state of the art" is
entirely the existing project's own prior-phase precedents (Phase 11 D-05, Phase 13 `taste_episode`, Phase
17 vision), all already current in the codebase as of 2026-07-15.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `asyncpg.Record` (installed version 0.31.0) supports `.get(key, default=None)` with the same missing-key-returns-default semantics as `dict.get` | Pattern 1 (`row.get("kind")`) | LOW — verified live via `'get' in dir(asyncpg.Record)` against the actual installed package in this environment; if a future asyncpg upgrade changed this, the existing codebase already has zero other `.get()` usages on Records to cross-check against, so a regression would surface immediately as a test failure, not a silent bug. |
| A2 | `vision_roast` salience `0.4` and decay `TASTE_DECAY_DAYS` (30d) are reasonable numeric defaults | Standard Stack § New | LOW — these are explicitly Claude's/planner's discretion per CONTEXT.md ("numeric knobs... per the Phase 11/13 discretion-on-numbers precedent"), not a locked decision; if wrong, it's a one-line config tune, not an architecture change. |
| A3 | Bare `asyncio.create_task` (not `make_task`) is the correct local-idiom choice for the new vision-memory call site | Pattern 2 | LOW — behaviorally safe either way (`distill_and_remember` never raises); worst case is slightly weaker observability if a background exception were ever thrown from something other than `distill_and_remember` itself (e.g. an `asyncio.CancelledError` on bot shutdown), which is an existing, unchanged risk shared by the three other bare-`create_task` distill sites already in production. |

**If this table is empty:** N/A — see entries above. All three assumptions are low-risk and independently
recoverable (config tune or task-wrapper swap), none touch the two locked D-01…D-04 decisions.

## Open Questions (RESOLVED)

None outstanding. The one "known wrinkle" CONTEXT.md flagged for researcher resolution (kind-threading to
the surface-bump path) is resolved above: cheap, via a service-local dict + `row.get("kind")`, not via a
`MemoryFact` field change.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio (existing, `requirements.txt`) |
| Config file | none — implicit defaults (per `.planning/codebase/TESTING.md`) |
| Quick run command | `pytest tests/test_memory.py -v` |
| Full suite command | `pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MEM-06 | `reinforce_memory_expiry` exists, is parameterized, uses `ANY($1)`, `GREATEST` | unit (pure/source-inspection, mirrors `TestWriteHelpersExist` pattern at `tests/test_database_phase11.py:50`) | `pytest tests/test_database_phase25.py::TestReinforceMemoryExpiryExists -x` | ❌ Wave 0 |
| MEM-06 | `recall()` groups top-k by resolved decay-days and calls the new helper once per group (mocked) | unit (mocked, extends `TestRecallService` in `tests/test_memory.py`) | `pytest tests/test_memory.py::TestRecallService -x` | ❌ Wave 0 (new test method; existing class extended) |
| MEM-06 | `test_returns_capped_facts_when_some_clear_floor` still passes after the new call is added | regression (existing test, monkeypatch list extended per Pitfall 2) | `pytest tests/test_memory.py::TestRecallService::test_returns_capped_facts_when_some_clear_floor -x` | ✅ exists, needs edit |
| MEM-06 (SC-1) | Live round-trip: insert two sweep-eligible-kind facts (equal age), surface only one via `recall()`, run `sweep()`, assert the surfaced one survives and the unsurfaced one is gone | integration (live-DB, `pool` fixture, CI pgvector container) | `pytest tests/test_database_phase25.py::test_reinforced_fact_survives_sweep_unreinforced_does_not -x` | ❌ Wave 0 |
| MEM-06 (SC-3) | A `milestone`-kind (or any salience ≥ 0.5) fact's `salience`/`hit_count`/`last_seen_at` are byte-identical after being surfaced via `recall()` (only `expires_at`/`last_surfaced_at`/`surface_count` may change) | integration (live-DB) | `pytest tests/test_database_phase25.py::test_recall_does_not_mutate_salience_or_hit_count -x` | ❌ Wave 0 |
| MEM-07 (SC-2) | `distill_and_remember(kind="vision_roast", exempt_numbers=False, ...)` round-trips: a safe roast line produces a row with `kind='vision_roast'`, `salience < 0.5`, correct `expires_at` horizon; a sensitive/number-bearing roast line produces ZERO rows (firewall enforced) | integration (live-DB, extends the existing `distill`/`remember` live-DB pattern) | `pytest tests/test_database_phase25.py::TestVisionRoastMemory -x` | ❌ Wave 0 |
| MEM-07 | `_maybe_fire_vision_roast` only spawns the memory-write task when `line is not None` and the reply send succeeded (mocked cog test, structural — mirrors existing Phase 17 glue tests, which are "untested-by-design" per `.planning/codebase/TESTING.md` for Discord glue, so this may be a code-review-verified acceptance criterion rather than an automated test) | manual/structural review | N/A — code review acceptance criterion, consistent with existing Phase 16/17 glue-layer precedent | — |
| MEM-06/07 (SC-3) | Full existing suite green with the new paths present-but-idle (no `vision_roast` kind ever written by any pre-existing test, no `recall()` call in any pre-existing test observes a changed `expires_at` on a non-target fact) | regression | `pytest` (full suite) | N/A — gate, not a new file |

### Sampling Rate
- **Per task commit:** `pytest tests/test_memory.py tests/test_database_phase25.py -v`
- **Per wave merge:** `pytest` (full suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_database_phase25.py` — new file; needs the `pool` live-DB fixture already provided by
      `tests/conftest.py` (no new fixture required — `conftest.py`'s `DROP TABLE ... user_memories CASCADE`
      teardown already covers the table this phase writes to, no `conftest.py` edit needed).
- [ ] `tests/test_memory.py` — extend `TestRecallService` with the new grouped-reinforcement mock test(s);
      edit `test_returns_capped_facts_when_some_clear_floor`'s monkeypatch block (Pitfall 2).
- [ ] No new pytest fixtures, no new framework install — `pytest`/`pytest-asyncio`/`pgvector/pgvector:pg16`
      (CI service container) are all already wired (`.github/workflows/ci.yml`).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Not touched — no auth surface in this phase. |
| V3 Session Management | No | Not touched. |
| V4 Access Control | Yes | `reinforce_memory_expiry`'s `UPDATE ... WHERE id = ANY($1)` has **no `user_id` scope** (mirrors `bump_surfaced`, which also has no `user_id` scope) — this is safe ONLY because the `ids` list is always derived from `recall()`'s own `search_memories(user_id=...)`-scoped result set, never from external/user-supplied ids. This is the existing `bump_surfaced` trust boundary, unchanged; the new helper must preserve it (never accept externally-sourced ids). |
| V5 Input Validation | Yes | `raw_text` fed to `distill()` for MEM-07 is Gemini-generated text (the roast line), not raw user input — but it indirectly reflects user-posted image content. The existing `is_sensitive`/`contains_number` firewall (unchanged) is the control; no new validation needed since the pipeline is reused verbatim. |
| V6 Cryptography | No | Not touched — no new secrets, tokens, or crypto operations. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via the new `reinforce_memory_expiry` UPDATE | Tampering | Fully parameterized (`$1`/`$2`), `ids` bound via `ANY($1)` array binding (asyncpg native array support — same pattern already proven safe at `bump_surfaced`/`evict_lowest_salience`). Never string-interpolate `ids` or `expires_at`. |
| Cross-user expiry tampering via a bug in the grouping logic | Tampering / Elevation of Privilege | The `ids` passed to `reinforce_memory_expiry` MUST always originate from the current call's own `top` (already `user_id`-scoped by `search_memories`) — never accept an externally-supplied id list. No user-facing surface can trigger this call with arbitrary ids (it is purely internal to `recall()`). |
| Raw-number/PII leakage into the `vision_roast` memory fact | Information Disclosure | `distill(exempt_numbers=False)` — the FULL firewall (`is_sensitive` + `contains_number`) applies, same as every Phase-11-era kind. No exemption is granted for this kind (unlike `taste_episode`'s narrow, justified exemption). |
| Appearance/identity-unsafe content persisted from a vision roast | Information Disclosure / reputational | Mitigated upstream, not in this phase's code: `build_vision_prompt`'s Phase-17 conduct clause already constrains the roast LINE (the source text) to never reference a real person's face/body/weight/identity; MEM-07 distills that already-constrained line, inheriting the safety property by construction (D-03). No new gate is added or needed in this phase. |

## Sources

### Primary (HIGH confidence — direct codebase read, 2026-07-15)
- `services/memory.py` (full file, 555 lines) — `recall`, `remember`, `distill`, `distill_and_remember`, `sweep`.
- `models/memory.py` (full file, 474 lines) — `MemoryFact`, `apply_floor`, `rerank`, `dedup_decision`, `compute_salience`, `choose_eviction`, `is_sensitive`, `contains_number`, `decay_predicate`.
- `database.py` lines 1390-1791 — all Phase 11/13 memory helpers (`search_memories`, `insert_memory`, `bump_memory_hit`, `refresh_memory_expiry`, `bump_surfaced`, `delete_expired_memories`, `count_user_memories`, `get_user_memories_for_eviction`, `evict_lowest_salience`, `list_user_memories`, `delete_all_user_memories`).
- `logic/taste.py` (full file, 204 lines) — `resolve_decay_days`, `summarize_taste`, `classify_artist`.
- `cogs/events.py` lines 1-45, 250-303, 555-699 — vision roast hook (`_maybe_fire_vision_roast`, `_generate_vision_roast`), existing ambient `distill_and_remember` call site, imports.
- `cogs/ai.py` / `cogs/music.py` (grep matches) — the other three existing `distill_and_remember` call sites, confirming both `make_task` and bare-`create_task` idioms coexist in the codebase.
- `personality/prompts.py` lines 303-316 — `build_vision_prompt`, confirming the Phase-17 conduct-clause claim (D-03's safety basis).
- `config.py` lines 165-263 — all memory/taste/vision config constants, confirming exact current values and line numbers.
- `tests/test_memory.py` (full-file grep + targeted reads, lines 80-870, 1816-1821) — every `MemoryFact(...)` construction site (keyword-only, confirming safe additive-field risk if ever needed), the `_DictRecord` stub class, and the exact set of `TestRecallService`/`TestRecallKindParam`/`TestRecallGuildScoped` tests that do/don't reach `recall()` step 7.
- `tests/test_database_phase11.py` lines 1-120, 200-250, 318-365 — the exact live-DB test pattern (`pool` fixture, `bump_surfaced`/`delete_expired_memories` round-trip shape) to extend for SC-1/SC-2.
- `tests/conftest.py` (full file) — confirms the live-DB `pool` fixture already covers `user_memories` teardown, no new fixture needed.
- Live environment check: `python -c "import asyncpg; print('get' in dir(asyncpg.Record))"` → `True` (asyncpg 0.31.0, the pinned project version per `requirements.txt`).
- `.planning/phases/25-smarter-memory/25-CONTEXT.md` — locked decisions D-01…D-04, canonical refs, discretion list.
- `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `.planning/codebase/TESTING.md` — requirement text, milestone sequencing, test-framework conventions.

### Secondary (MEDIUM confidence)
- None — this phase required no external documentation lookup (no new library/framework/service).

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies; every recommended component is an existing, already-tested project primitive read directly from source.
- Architecture: HIGH — both patterns are directly derived from proven in-repo precedents (D-05 self-refresh, Phase 13 new-kind pattern, four existing `distill_and_remember` call sites) with live line-number verification.
- Pitfalls: HIGH — Pitfall 2 (test-mock breakage) was verified by actually reading the specific test fixtures and confirming which ones reach the affected code path; Pitfall 1 (salience-floor interaction) was verified by reading the actual sweep SQL and salience weight table.

**Research date:** 2026-07-15
**Valid until:** No external-library expiry applies (internal-only research); revalidate if `services/memory.py`, `database.py` memory helpers, or `cogs/events.py::_maybe_fire_vision_roast` are touched by an intervening phase before Phase 25 executes.
