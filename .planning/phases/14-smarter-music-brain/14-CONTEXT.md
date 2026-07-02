# Phase 14: Smarter Music Brain - Context

**Gathered:** 2026-07-02
**Status:** Ready for planning

> ⚠️ **Session note:** The user launched `/gsd:discuss-phase 14`, was presented the
> domain boundary and four gray areas, then stepped away before selecting any. **D-01
> through D-08 below were decided by Claude on the user's behalf using best judgment**,
> each grounded in the locked BRAIN-01/02/03 requirement text, Success Criterion 4
> (multi-user-safety), and the Phase 11/13 accuracy-firewall precedent. They are
> conservative, tunable defaults — the user should skim the **"decided on user's behalf"**
> items and revise before `/gsd-plan-phase 14` if any feel wrong. All numeric values
> (windows, caps, thresholds) remain Claude's-discretion / spike territory (mirrors
> Phase 11/13). Two genuine correctness questions are flagged for the planner at the end.

<domain>
## Phase Boundary

Dexter's **auto-queue, a new discovery command, and jam assist become taste-aware** —
consuming the Phase 13 `taste_episode` memory substrate plus **live SQL** (skip history,
artist co-occurrence) to act like a better DJ instead of a bland server-average shuffler.
This is the **first consumer phase** of the v1.3 "Taste Brain" milestone: Phase 13 wrote
the taste substrate; Phase 14 makes three surfaces *read a taste signal and change a
decision*. Everything stays **Gemini-in-the-loop + SQL — never a trained ML model**.

**In scope:**
- **BRAIN-01** — taste-aware auto-queue: recent `was_skipped` history becomes a **negative
  hint** so auto-queue stops re-suggesting tracks/artists the room keeps skipping, and the
  room's `taste_episode` memory feeds in as a **positive hint**.
- **BRAIN-02** — a **discovery command** surfacing artist/genre adjacency from *grounded
  co-occurrence SQL* over `song_history` / `user_artist_counts` (zero hallucination, zero
  cost, multi-user-safe aggregate).
- **BRAIN-03** — **generative jam assist** ("continue this jam"): Gemini suggests additions
  to a server jam using taste context, every suggestion passing `logic/autoqueue.py`
  token-set-containment validation before being offered.

**Out of scope (belongs to later phases / deferred):**
- `/roast @user` / `/ask` grounding in recalled memory, `/memory` view + forget → **Phase 15**.
- Proactive/unprompted memory surfacing → **Phase 16**. Vision roasting → **Phase 17**.
- Any *new* memory `kind` or write path (Phase 14 is read-only against the taste substrate).
- A trained/learned recommender, embeddings-based track similarity, or any new dep/table/
  limiter (milestone tight-scope discipline; zero new infra).
- Embedding any SQL-known number into memory (permanent anti-feature — accuracy firewall).

</domain>

<decisions>
## Implementation Decisions

### Negative-hint shape for auto-queue (BRAIN-01)

- **D-01 (decided on user's behalf):** The negative signal is a **guild-scoped, aggregate
  "recently skipped" block injected into the recommendation prompt** — a number-free list of
  recently-skipped **titles + artists** sourced from `song_history WHERE was_skipped = true
  AND guild_id = $1` over a recent window (directional **~7 days / ~15 rows**). The prompt
  gains an "avoid these — the server keeps skipping them" section alongside the existing
  recent-plays block. **Guild-collective, not per-listener** — auto-queue is already a
  guild-scoped surface and Criterion 4 requires aggregate/server-safe signals, so the room's
  collective skips are the correct unit (no cross-user leak, no "who's in voice right now"
  fragility). *(Rejected: per-active-listener skip lists — leak risk + complexity for a
  shared queue.)*
- **D-02 (decided on user's behalf — defense in depth):** Keep the negative hint primarily a
  **soft prompt instruction** (preserves Gemini-in-the-loop, BRAIN-01), but add a **lightweight
  hard post-filter**: after search, reject a candidate whose normalized artist token-set
  matches a recently-skipped artist. The existing post-search `validate_youtube_match`
  (hallucination guard) stays unchanged and runs independently. Belt-and-suspenders mirrors
  the Phase 13 pre-bucket-plus-backstop discipline.

### Positive taste signal in auto-queue (BRAIN-01)

- **D-03 (decided on user's behalf — the multi-user-safe blend):** Auto-queue recalls the
  **`taste_episode` memory of each non-bot member currently in the voice channel** — reusing
  the exact in-voice member set already computed for the `auto_queue_ignored` write
  (`cogs/ai.py` ~line 404) — and blends them as a collective **"the room tends to like…"**
  positive context in the prompt. This is multi-user-*safe* because it is scoped to
  consenting-present members' shared session (the same basis as the collective skip signal),
  never surfacing one member's data into an unrelated context. Total injected taste facts are
  **capped** (directional **~3–4**, planner/spike-tuned) to keep the prompt lean and protect
  the `_embed_limiter` (60 RPM) budget. If no member has a taste episode above the recall
  floor, the block is omitted and behavior is byte-identical to today (Pitfall 8: "no memory
  beats a wrong memory"). *(See Open Question 1 — recall() currently returns mixed kinds.)*

### Discovery command (BRAIN-02)

- **D-04 (decided on user's behalf):** A new **`/discover`** slash command that is
  **invoker-anchored, server-adjacency-grounded**: it reads the **invoker's** top artist(s)
  from `user_artist_counts`, then computes **server-wide co-occurrence adjacency** from
  `song_history` (artists that co-occur with the anchor within the same guild's listening) to
  surface **1–3 adjacent artists/genres**. The **recommendation itself is 100% SQL-derived**
  (zero hallucination — Criterion "never a hallucinated recommendation"); **Gemini only
  supplies Dex's voice/commentary wrapping the SQL result**, never the picks. This keeps it
  personal-feeling while the *adjacency* stays an aggregate that never exposes a specific
  other user's list (Criterion 4). *(Rejected: Gemini-generated recommendations — would
  violate the zero-hallucination requirement.)*
- **D-05 (decided on user's behalf):** `/discover` is **actionable but confirm-first** —
  it presents the adjacent artist(s) with Dex commentary and **offers to queue** one (button
  / follow-up), rather than silently auto-queuing. Cog placement (`cogs/music.py` since it
  can queue, vs `cogs/ops.py`) is planner discretion; lean `music.py`. New empty/low-history
  state returns an in-character "not enough listening yet" message rather than erroring.

### Jam assist surface (BRAIN-03)

- **D-06 (decided on user's behalf):** A **new `/jam suggest <name>` subcommand** (sibling of
  the existing `save`/`add`/`load`/`list`/`delete` in `cogs/library.py`) — not a flag
  overloading `/jam add`. It seeds Gemini with the **named jam's existing tracks as taste
  context**, requests N additions, and **validates every suggestion through
  `logic/autoqueue.py::validate_youtube_match`** against real YouTube search results before it
  is ever offered (BRAIN-03 hard requirement).
- **D-07 (decided on user's behalf — trust discipline):** `/jam suggest` is
  **propose-and-confirm**: Dex shows the validated candidate additions and the user confirms
  before anything is written. On confirm, validated tracks are **appended to the jam
  snapshot** (consistent with `/jam add` semantics — a jam is a persisted per-guild JSONB
  snapshot), with an option to also queue them now. It never silently mutates a shared
  server artifact. Suggestions that fail validation are dropped and, if none survive, Dex
  says so in character rather than committing garbage.

### Multi-user-safety (Criterion 4 — cross-cutting)

- **D-08 (decided on user's behalf):** Every new aggregate query is **guild-scoped or
  invoker-anchored-with-aggregate-adjacency**, following the exact param-binding + scoping
  discipline of Phase 13's `get_user_artist_activity` / `get_user_skip_rate` (bound `$N`
  positional params, never string interpolation; `WHERE guild_id` and/or `WHERE user_id`
  scoping; index-friendly `queued_at >` bounds against `idx_history_guild`/`idx_history_user`).
  No query returns one user's individual listening rows into another user's result. This is a
  **verification target**, not just a convention.

### Claude's Discretion (explicit — do NOT re-ask the user)

- All numeric values are directional priors, tuned during planning/spike + live observation
  (mirrors Phase 11/13): skip-window lookback (~7 days / ~15 rows), injected-taste-fact cap
  (~3–4), number of `/discover` adjacents (1–3), number of `/jam suggest` candidates, and the
  co-occurrence "same session/window" definition.
- Exact SQL shape of the new `get_recently_skipped` (guild, window) helper and the co-occurrence
  adjacency helper over `song_history` / `user_artist_counts`, plus the prompt-template edits to
  `build_recommendation_prompt` and the new jam/discovery prompt builders, are planning detail.
- Cog placement of `/discover` (`music.py` vs `ops.py`) — planner's call.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements (this phase)
- `.planning/ROADMAP.md` §"Phase 14: Smarter Music Brain" — goal, 4 success criteria, deps.
- `.planning/REQUIREMENTS.md` — BRAIN-01, BRAIN-02, BRAIN-03 (+ Out of Scope table).

### Phase 13 foundation (the substrate being consumed — binding on mechanics)
- `.planning/phases/13-semantic-music-memory/13-CONTEXT.md` — taste_episode kind, self-refresh
  design (D-05 there), accuracy-firewall bridge, salience/decay tiers.
- `database.py` `get_active_taste_users` / `get_user_artist_activity` (~1284–1360) — the
  **scoping + param-binding + index-friendly template** every new Phase 14 aggregate must mirror
  (D-08); also `get_user_skip_rate` (~1255), `get_leaderboard_skips` (~453), `mark_song_skipped`
  (~336), `get_recent_songs` (~350).
- `config.py` §"Phase 11/13" `MEMORY_*` / `TASTE_*` knobs — new Phase 14 knobs live alongside.

### Auto-queue + validation seam (the surfaces being modified)
- `cogs/ai.py::try_auto_queue` (~255–443) — the auto-queue flow; note the in-voice member set
  computed for the `auto_queue_ignored` write (~404) that D-03 reuses, and the
  `should_start_playback` / voice-client-is-ground-truth gotcha (~372).
- `logic/autoqueue.py::validate_youtube_match` — token-set containment (reuse verbatim for
  BRAIN-03; do NOT reimplement or swap to difflib — D-12 anti-pattern).
- `personality/prompts.py::build_recommendation_prompt` (~183) + `MUSIC_RECOMMENDATION_PROMPT`
  — extended with the negative/positive hint blocks (D-01/D-03).
- `services/memory.py::recall` (~61) — per-user, returns `list[str]`, **currently kind-agnostic**
  (mixes all kinds) — see Open Question 1.

### Jam surface (BRAIN-03)
- `cogs/library.py` §"/jam group" (~692+) — `jam_save` / `jam_add` subcommand pattern +
  snapshot serialization (`save_jam`, `to_dict()`) to clone for `/jam suggest`.

### v1.3 research (authoritative for mechanics)
- `.planning/research/SUMMARY.md`, `FEATURES.md`, `ARCHITECTURE.md`, `PITFALLS.md` — esp. the
  Gemini-in-the-loop-not-ML ruling, the co-occurrence-SQL grounding, and the
  hallucination-validation reuse.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `logic/autoqueue.py::validate_youtube_match` — pure, mock-free token-set containment; reused
  verbatim for BRAIN-03 jam-suggestion validation (already used by auto-queue).
- `services/memory.py::recall(user_id, guild_id, query_text)` — per-user ANN recall returning
  `list[str]`; the positive-taste source for D-03 (pending a kind filter — OQ1).
- `database.py` Phase 13 helpers — the scoping/param-binding template (D-08) plus existing
  skip helpers (`mark_song_skipped`, `get_user_skip_rate`, `get_leaderboard_skips`).
- `cogs/library.py` /jam subcommand group — the surface `/jam suggest` extends.

### Established Patterns
- **Gemini supplies voice, SQL supplies facts** (accuracy firewall, Critical Rule 12) — numbers
  and recommendations are SQL-grounded; Gemini only wraps them in Dex's tone.
- **Guild-scoped / invoker-anchored aggregates only** (Criterion 4) — mirror `WHERE guild_id`/
  `WHERE user_id` scoping + bound `$N` params; never merge cross-user rows into one result.
- **Propose-and-confirm before mutating shared artifacts** (jam snapshots).
- **Voice-client is ground truth for "audio flowing"** (`should_start_playback`), not
  `queue.is_playing` (scar #2) — auto-queue edits must not regress this.

### Integration Points
- New `get_recently_skipped(pool, *, guild_id, since/limit)` helper in `database.py` feeding the
  D-01 negative-hint prompt block.
- New co-occurrence adjacency helper in `database.py` over `song_history`/`user_artist_counts`
  feeding `/discover` (D-04).
- New prompt builders (jam-suggest, discover-commentary) in `personality/prompts.py`; extended
  `build_recommendation_prompt` for the negative/positive blocks.
- `/discover` command in a music cog; `/jam suggest` subcommand in `cogs/library.py`.
- New Phase 14 config knobs (windows, caps) in `config.py` alongside Phase 11/13.

</code_context>

<specifics>
## Specific Ideas

- **Feel target:** auto-queue should feel like a DJ who *noticed you kept skipping the sad
  indie stuff and stopped playing it* — not a random shuffler. `/discover` should feel like
  "you're into X; people here who like X also spin Y — want it?" grounded in real server data,
  never invented. `/jam suggest` should feel like Dex reading the room's mixtape and offering
  genuinely on-vibe additions, in character, never garbage (validation-gated).
- **The clean split that satisfies Criterion 4:** guild-collective signals (skips, in-room
  taste blend) drive the shared auto-queue; invoker-anchored + aggregate-adjacency drives the
  personal-feeling `/discover`; the jam's own tracks drive `/jam suggest`. No surface merges
  one user's private rows into another user's output.

</specifics>

<deferred>
## Deferred Ideas

- **Per-active-listener (non-aggregate) auto-queue personalization** — rejected for Phase 14
  in favor of the guild-collective blend (D-01/D-03) to preserve multi-user-safety. Revisit
  only if collective auto-queue feels too bland after live observation.
- **Embeddings-based track/artist similarity for discovery** — out of scope; `/discover` uses
  SQL co-occurrence only (zero new infra, zero hallucination). A learned recommender is a
  future-milestone idea, not v1.3.
- **`/roast @user` / `/ask` / `/memory` memory grounding** → Phase 15 (explicitly next phase).
- **Proactive unprompted taste callbacks** → Phase 16.

None of the above are lost — each has a home in a later phase or the backlog.

</deferred>

<open_questions>
## Open Questions for the Planner (flag, don't guess)

1. **Kind-scoped recall for the positive taste hint (D-03).** `services/memory.py::recall`
   currently returns the top facts across **all** kinds (milestone / late_night /
   auto_queue_ignored / taste_episode) mixed. For the auto-queue positive-taste blend we want
   **`taste_episode` facts specifically** — a milestone or late_night fact is the wrong signal
   for "what music to queue." Planner must decide: add a `kind` filter param to `recall()` (or
   a thin `recall_taste()` variant / post-filter on the returned rows). Confirm whichever path
   keeps Phase 11/15 recall behavior byte-identical when unfiltered. **This is the main
   design question in BRAIN-01.**

2. **Co-occurrence definition for `/discover` (D-04).** "Artists that co-occur with the anchor"
   needs a concrete, index-friendly SQL definition (same guild + same rolling window? same
   user-session? simple guild-wide artist adjacency?). Must stay aggregate/server-safe
   (Criterion 4) and index-friendly against `idx_history_guild`. Pick the simplest grounded
   definition that yields non-hallucinated adjacency; validate it returns sensible results on
   real `song_history` before committing to it.

</open_questions>

---

*Phase: 14-smarter-music-brain*
*Context gathered: 2026-07-02*
