# Phase 13: Semantic Music Memory - Context

**Gathered:** 2026-07-02
**Status:** Ready for planning

> ⚠️ **Session note:** The user selected all four gray areas to discuss and answered the
> first (taste-episode triggers) before stepping away. **D-02 through D-08 below were decided
> by Claude on the user's behalf using best judgment**, each grounded in the locked Phase 11
> accuracy-firewall precedent and the v1.3 research pitfalls. They are conservative, tunable
> defaults — the user should skim the **"Decided on user's behalf"** items and revise before
> `/gsd-plan-phase 13` if any feel wrong. The numeric values remain Claude's-discretion/spike
> territory regardless (mirrors Phase 11).

<domain>
## Phase Boundary

Dexter's **listening history** (not chat banter) becomes a retrievable, number-free semantic
memory — a new `taste_episode` `kind` distilled from `song_history` / `user_artist_counts` onto
the **existing** `user_memories` pgvector store, written by a **new background `@tasks.loop`**
on its own schedule, reusing `MemoryService.distill_and_remember()` end-to-end.

This is the **foundation phase** of v1.3 "Taste Brain" — every downstream feature (Phase 14
taste-aware auto-queue/discovery/jams, Phase 15 RAG-into-`/roast`/`/ask`, Phase 16 proactive
callbacks) reads the substrate this phase writes. Per research, Phase 13 **skips the dedicated
research-phase**: it is a direct, kind-agnostic extension of the shipped Phase 11 plumbing —
zero code change needed in `services/memory.py` / `models/memory.py`, zero new tables, deps,
extensions, limiters, or schedulers.

**In scope:** TASTE-01 (number-free taste_episode facts distilled from real listening),
TASTE-02 (own salience base weight + decay tier, distinct from Phase 11 defaults), TASTE-03
(new background task on a distinct schedule, no Neon thundering-herd).

**Out of scope (belongs to later phases / deferred):** any *consumer* of taste memory
(auto-queue negative hints → Phase 14; `/roast`/`/ask`/`/memory` → Phase 15; proactive
surfacing → Phase 16); a distinct `taste_shift` kind (deferred, see below); embedding any
SQL-known number (permanent anti-feature — accuracy firewall); historical backfill (start
empty, accumulate forward — mirrors Phase 11).

</domain>

<decisions>
## Implementation Decisions

### What is a taste episode (TASTE-01)

- **D-01 (user-selected):** Three listening patterns are worth distilling into a taste episode.
  The user explicitly chose these and dropped a fourth:
  1. **Artist obsessions / binges** — a burst of repeated plays of one artist ("someone went
     deep on the killers this week"). Most roastable; strongest positive/negative DJ signal.
  2. **New-artist arrivals** — an artist/genre showing up meaningfully for the first time
     ("someone started getting into phonk out of nowhere"). Feeds discovery + "you used to be
     normal" roasts.
  3. **Steady favorites** — durable long-run preferences ("someone always comes back to mac
     demarco"). Slower-moving, higher-confidence taste.
  - **Dropped by user:** *late-night listening character* — correctly rejected as redundant
    with the existing `late_night` memory kind (Phase 11). Do NOT add it.

- **D-02 (decided on user's behalf — the accuracy-firewall bridge):** The distill task
  **pre-buckets raw counts into qualitative bands BEFORE Gemini sees them** ("played heavily" /
  "a few times" / "dropped off" / "new this week"), so **no number ever reaches the prompt**.
  The existing `contains_number()` distill backstop then acts as belt-and-suspenders, not the
  primary defense. Rationale: the accuracy firewall is a *hard constraint* (Critical Rule 12 /
  Pitfall "embedding SQL-known numbers"); feeding raw counts and trusting a single gate pushes
  numbers right up to the firewall and one gate failure leaks a count. Pre-bucketing keeps
  numbers structurally out of the pipe. *(Rejected alternative: feed raw counts, trust the
  gate.)*

### Staleness / salience / decay tier (TASTE-02)

- **D-03 (decided on user's behalf):** Taste episodes **decay FASTER than the 90-day
  general-fact default** (`MEMORY_DECAY_DAYS = 90`). Directly mitigates research **Pitfall 5**
  — "a 'likes artist X' fact has a much shorter half-life than a milestone/personality fact;
  stale taste surfaced as current." Introduce a distinct `TASTE_DECAY_DAYS` (directional
  starting point **~30 days**, spike/observation-tunable).
- **D-04 (decided on user's behalf):** Taste episodes carry their **own salience base weight**
  set **below `MEMORY_DECAY_SALIENCE_FLOOR` (0.5)** so they are genuinely *eligible for expiry*
  by the existing sweep (which retains rows where `salience >= floor` past `expires_at`).
  Directional starting point **~0.4** — comparable to a preference signal but not "permanent."
  Add `"taste_episode"` to `MEMORY_SALIENCE_BASE_WEIGHTS`.
- **D-05 (decided on user's behalf — the self-refresh design intent):** Durable "steady
  favorites" stay alive **not** by having high salience, but by being **re-written each cycle
  while still true** — every fresh distillation resets `created_at`/`expires_at`, so genuine
  long-run tastes self-refresh while fads age out. This is why a low salience + short decay
  window is safe: it does not lose durable taste, it just requires taste to keep being true.
  Dedup (`MEMORY_DEDUP_THRESHOLD = 0.92`) already prevents duplicate rows on re-write —
  **planning must verify** re-distilling a still-true taste refreshes the timestamp rather
  than being silently dropped as a near-dup (open question for the planner; see below).

### Distill cadence & window (TASTE-03)

- **D-06 (decided on user's behalf):** A **daily** module-scope `@tasks.loop`
  (`taste_distill_batch`, sibling of `memory_distill_batch` / `memory_sweep`), following the
  `make_task`/`.error`/`before_loop wait_until_ready` convention. Scheduled at a **distinct
  UTC hour** clear of the existing staggered loops (hourly `cache_cleanup`, `memory_sweep`
  02:30, `memory_distill_batch` 03:00, `ytdlp_update` 04:00). Directional slot **~05:00 UTC**
  (`TASTE_DISTILL_BATCH_HOUR`) — no thundering-herd on the Neon pool.
- **D-07 (decided on user's behalf):** The task reads a **rolling recent lookback window** of
  `song_history` per active user (directional **~7 days**) to detect obsessions/new arrivals
  against a longer baseline for "steady." Reads structured tables **only** — never the message
  buffer (that is `memory_distill_batch`'s job; keeps the two write paths distinct per TASTE-03).
- **D-08 (decided on user's behalf):** A **min-activity threshold** gates per-user distillation
  (directional **~5–8 tracks in the window**) so light/inactive users don't trigger noise facts
  or waste `_embed_limiter` (60 RPM) / priority-2 chat calls. Skip users below the floor.

### One taste kind or two

- **D-09 (decided on user's behalf):** **One kind — `taste_episode`** for v1.3. The
  research-flagged optional second kind (`taste_shift`, for "dropped an artist / pivoted
  genre") is **deferred**. A pivot can be expressed inside a `taste_episode` narrative ("all in
  on phonk lately, dropped the indie stuff") without a second salience/decay tier and a second
  write path. Keeps the foundation lean, matching the milestone's tight-scope discipline.

### Claude's Discretion (explicit — do NOT re-ask the user)

- All numeric values are directional priors, tuned during planning/spike + live observation
  (mirrors the Phase 11 numeric-defaults precedent): `TASTE_DECAY_DAYS` (~30), taste_episode
  base salience (~0.4), `TASTE_DISTILL_BATCH_HOUR` (~05:00 UTC), lookback window (~7d),
  min-activity threshold (~5–8 tracks), obsession/new-arrival/steady detection thresholds, and
  the exact qualitative band boundaries for D-02.
- Exact SQL shape of the taste-aggregate helper(s) over `song_history` / `user_artist_counts`,
  and the raw_text template handed to `distill_and_remember`, are implementation detail for
  planning.

### Open questions for the planner (flag, don't guess)

- **Dedup vs self-refresh (from D-05):** confirm that re-distilling a still-true steady favorite
  refreshes its `expires_at` rather than being silently rejected by the 0.92 dedup threshold as a
  near-duplicate. If dedup blocks the refresh, steady favorites would wrongly age out — needs an
  explicit "touch/refresh on dedup-hit" path or an exemption. **This is the one correctness risk
  in the phase's design.**

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements (this phase)
- `.planning/ROADMAP.md` §"Phase 13: Semantic Music Memory" — goal, 4 success criteria, deps.
- `.planning/REQUIREMENTS.md` — TASTE-01, TASTE-02, TASTE-03 (+ Out of Scope table).

### v1.3 research (authoritative for mechanics — HIGH confidence, converged 4 ways)
- `.planning/research/SUMMARY.md` — executive synthesis; §"Phase 13" build order; the
  flavor-vs-numbers split; "skip research-phase" ruling; the taste-salience/decay gap flag.
- `.planning/research/FEATURES.md` — must/should/anti-feature breakdown for taste memory.
- `.planning/research/ARCHITECTURE.md` — verified seams: new `taste_distill_batch` loop,
  `MEMORY_SALIENCE_BASE_WEIGHTS` extension, structured aggregate helper placement.
- `.planning/research/PITFALLS.md` — esp. **Pitfall 5** (stale taste surfaced as current) and
  the accuracy-firewall/number-embedding pitfall driving D-02/D-03/D-04.

### Phase 11 precedent (the plumbing being extended — binding on mechanics)
- `.planning/phases/11-rag-long-term-memory/11-CONTEXT.md` — accuracy firewall (D-01/D-06
  there), salience hybrid (D-07 there), distill-boundary (D-09/D-10 there), decay/cap hygiene.
- `services/memory.py` — `distill()`, `distill_and_remember(kind=, base_salience=)`, `remember()`,
  `sweep()` (all kind-agnostic; **reuse unchanged**).
- `models/memory.py` — `MemoryFact` + pure decay/salience logic (extend, don't fork).
- `config.py` §"Phase 11: RAG Long-Term Memory" (lines ~160–187) — `MEMORY_*` knobs +
  `MEMORY_SALIENCE_BASE_WEIGHTS`; add the taste knobs alongside these.
- `bot.py` `memory_distill_batch` (~808) / `memory_sweep` (~903) — the exact `@tasks.loop`
  template (schedule / `before_loop` / `.error` / `getattr` guards) for `taste_distill_batch`.
- `database.py` `SCHEMA_SQL` + K-04 Neon pool tuning — new aggregate helper follows existing
  query-helper conventions; no schema change.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `services/memory.py::distill_and_remember(user_id, guild_id, raw_text, kind, base_salience)`
  — kind-agnostic; the taste task calls it with `kind="taste_episode"`. **No change needed.**
- `services/memory.py::distill()` — already enforces number-free (`contains_number()`) and
  sensitivity (`is_sensitive()`) stop-ship backstops; the D-02 pre-bucketing sits *upstream* of it.
- `_embed_limiter` (separate 60 RPM) + priority-2 chat calls — background taste writes use these,
  never the 15 RPM user budget (Critical Rule 11).
- `config.MEMORY_SALIENCE_BASE_WEIGHTS` dict + `MEMORY_DECAY_SALIENCE_FLOOR` sweep gate — extend
  with `"taste_episode"`; D-04 deliberately places it below the floor.

### Established Patterns
- Module-scope `@tasks.loop` in `bot.py` with `getattr(bot, "memory_service", None)` no-op guard,
  `before_loop → wait_until_ready`, and a `.error` handler calling `_post_loop_error` — clone for
  `taste_distill_batch`.
- Staggered daily schedules to protect the Neon pool (02:30 / 03:00 / 04:00 UTC) — pick a clear
  slot (~05:00) per D-06.
- Number/sensitivity firewall: numbers come from live SQL, memory holds episodes only (Phase 11).

### Integration Points
- New daily loop `taste_distill_batch` registered alongside the other loops in `bot.py`
  `on_ready`/setup (wherever `memory_distill_batch` is started).
- New structured aggregate helper(s) in `database.py` over `song_history` /
  `user_artist_counts` feeding the pre-bucketing step (D-02).

</code_context>

<specifics>
## Specific Ideas

- **Feel target:** the taste episode is roast/DJ *ammo* in Dex's voice — "someone went all in on
  the killers this week, then swore off them by friday" — never a stat line. Numbers, when they
  ever appear in output, come from live SQL at the consuming surface (Phase 14/15), not from the
  embedded fact.
- **Self-refresh over permanence (D-05):** durable taste survives by staying true and being
  re-written, not by never expiring. Fads age out on their own. This is the intended emergent
  behavior of low-salience + short-decay + dedup-touch.

</specifics>

<deferred>
## Deferred Ideas

- **Distinct `taste_shift` kind** — a separate memory kind for "dropped an artist / pivoted
  genre" with its own salience/decay tier and write path. Deferred from v1.3 (D-09): a pivot can
  live inside a `taste_episode` narrative for now. Revisit if pivot-roasts feel underpowered
  after live observation.
- **Late-night listening as a taste kind** — rejected by the user as redundant with the existing
  `late_night` kind. Not a future item unless the two are ever unified.
- **Salience reinforcement for frequently-recalled taste** (MEM-R1) — already milestone-out-of-scope
  (→ v1.4). Noted so the self-refresh design (D-05) isn't confused with reinforcement.

</deferred>

---

*Phase: 13-semantic-music-memory*
*Context gathered: 2026-07-02*
