# Phase 15: RAG Reach - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning

> ⚠️ **Session note:** The user launched `/gsd:discuss-phase 15`, was presented the
> domain boundary + a key scouting finding (RAG-01/02 already wired in Phase 11) and
> three gray areas. The user **locked the `/memory` view shape (D-02) directly**, and
> for the recall-cadence (D-01) and forget-granularity (D-03) areas asked for Claude's
> educated recommendation and a re-ask — then stepped away before answering the re-ask.
> **D-01 and D-03 below are Claude's recommendations, adopted on the user's behalf** —
> conservative, requirement-anchored, and tunable. They mirror the Phase 14 "decided on
> user's behalf" pattern. The user should skim the **recommendation** items and revise
> before `/gsd-plan-phase 15` if any feel wrong. All numeric values remain
> Claude's-/planner's-discretion (mirrors Phase 11/13/14).

<domain>
## Phase Boundary

Long-term memory becomes **directly visible and controllable**. Two of the four
requirements are **already substantially shipped by Phase 11** and this phase
verifies + tunes them; the other two are **genuinely new user-facing surfaces**:

**Already wired in Phase 11 (verify + cadence-tune — see D-01):**
- **RAG-01** — `/roast @user` already recalls the **target's** memory
  (`cogs/ai.py:214`, `recall(str(target.id), ...)`), correctly target-scoped, feeding
  `build_chat_prompt(memories=...)` alongside the live SQL `user_summary` stat.
- **RAG-02** — `/ask` already recalls the **invoker's** memory (`cogs/ai.py:136`,
  `recall(str(interaction.user.id), ...)`), with the byte-identical fallback via
  `memories or None`.
  Both currently fire only behind the `MEMORY_CALLBACK_CHANCE` (0.35) random gate.

**Genuinely new in Phase 15:**
- **RAG-03** — a `/memory` command giving the user an in-character, read-only view of
  what Dexter remembers about them. Does not exist today.
- **RAG-04** — `/memory forget` hard-delete (rows **and** embeddings verifiably gone).
  Does not exist today — Phase 11 explicitly **deferred** `/forget`. Only *internal*
  sweep / cap-evict DELETEs exist (`database.py:1140` per-id, `:1196` decay sweep).
  This is **the trust escape hatch** Phase 16 hard-depends on.

**In scope:**
- Confirm RAG-01/02 satisfy the requirement text and apply the D-01 cadence change.
- New `/memory` read-only view (verbatim stored facts + Dex framing — D-02).
- New `/memory forget` nuke-all hard-delete with confirmation (D-03) + a new
  `delete_all_user_memories` DB helper.
- A "verifiably gone" integration test (Success Criterion 4).

**Out of scope (belongs to later phases / deferred):**
- Proactive/unprompted memory surfacing + per-user callback opt-out → **Phase 16**
  (hard-blocked on RAG-04 shipping first — do not reorder).
- Vision / multimodal roasting → **Phase 17**.
- Kind-aware / per-item **selective** forget → deferred to backlog (see Deferred Ideas;
  layers on top of nuke-all later without rework).
- Any new memory `kind`, write path, dependency, table, or limiter (milestone
  tight-scope discipline; zero new infra).
- Embedding any SQL-known number (permanent anti-feature — accuracy firewall).

</domain>

<decisions>
## Implementation Decisions

### Recall cadence for explicit `/roast` & `/ask` (RAG-01 / RAG-02)

- **D-01 (Claude recommendation, adopted on user's behalf):** **Always ground the
  explicit commands.** Remove the `MEMORY_CALLBACK_CHANCE` (0.35) random gate from
  `/roast` and `/ask` **specifically** — these are deliberate, opted-in invocations, so
  a 65%-chance no-op reads as *flaky*, not *tasteful*. Rely on the two protections that
  already exist: the `MEMORY_SIMILARITY_FLOOR` (0.70) is the real "when relevant" gate
  RAG-02's text asks for, and injected memories remain **candidate ammo the model may
  NOOP** (Phase 11 D-06). **Keep the 0.35 random gate on the *ambient / unprompted*
  surfaces only** — `cogs/events.py:128` (ambient roast) and `cogs/music.py:1272`
  (notable-event roast) — where "rarity hits harder" (Phase 11 D-04) still applies.
  RAG-02's **byte-identical guarantee is preserved**: floor returns nothing →
  `memories=[] → None` → identical prompt. *(Rejected: keep-occasional-everywhere —
  makes an explicit command feel broken; RAG-01's "grounds its roast" reads as a
  reliable behavior, not a dice roll.)*
  **This is a recommendation — user asked to re-decide; revise if the rare-callback feel
  is preferred even on explicit commands.**

### `/memory` view — content & visibility (RAG-03)

- **D-02 (LOCKED by user):** `/memory` shows the **verbatim stored fact strings** (the
  real ammo) wrapped in a short **in-character Dex intro/outro** — NOT a Gemini-rewritten
  paraphrase. Rationale: this is a **trust / transparency** surface — the user must see
  *exactly* what is stored (and therefore exactly what `/memory forget` will erase). A
  paraphrase could distort or hide the actual rows, defeating the escape-hatch purpose.
  The view is **read-only** and should be **ephemeral** (visible only to the invoker —
  memory is personal). Empty state returns an in-character "i don't remember anything
  about you yet" rather than an error.

### `/memory forget` — granularity & safety (RAG-04)

- **D-03 (Claude recommendation, adopted on user's behalf):** **Nuke-all + confirm.**
  `/memory forget` wipes **all** of the invoker's stored memories behind an **ephemeral
  confirmation** (button) with a **count preview** ("i've got 23 things on you. wipe them
  all? no takebacks."). New `delete_all_user_memories(pool, user_id)` DB helper, scoped
  `WHERE user_id = $1` (mirrors the T-11-04c cross-user guard — a bug can never touch
  another user's rows). Deleting the row deletes its `embedding` column in the same row,
  so "rows **and** embeddings verifiably gone" is inherent; proven by an integration test
  (`remember → forget → recall == []`, Success Criterion 4).
  **The taste-erasure tension is dissolved by design:** forget deletes the *memory vector
  store*, NOT the underlying `song_history` play logs (which it does not touch), so the
  Phase 14 taste-brain **re-distills gracefully** from untouched SQL on the Phase 13
  background schedule. The escape hatch stays clean/total/verifiable (what Phase 16
  requires) while the DJ recovers on its own. *(Rejected for Phase 15: kind-aware and
  per-item selective forget — weaker privacy promise, bigger footgun on the one path
  where a bug = data loss / cross-user deletion, and larger surface for marginal benefit;
  deferred to backlog, can layer on nuke-all later.)*
  **This is a recommendation — user asked to re-decide; revise if selective/kind-aware
  forget is wanted in-phase.**

### Claude's / Planner's Discretion (do NOT re-ask the user)

- **Command surface shape** — likely a `/memory` `app_commands.Group` with `view` +
  `forget` subcommands (mirrors `/jam` / `/playlist` groups in `cogs/library.py`), where
  "`/memory`" colloquially means `/memory view`. Cog placement (new `cogs/memory.py` vs
  folding into `cogs/ai.py` near the recall wiring) is planner's call — lean a small new
  cog for cohesion. Note discord.py cannot have both a bare group invocation and
  subcommands, so bare-`/memory`-as-view is a naming nicety, not a literal constraint.
- **View rendering detail** — which fields beyond the fact string to surface (kind? date?
  salience?); lean **minimal** (facts + framing). A user can hold up to
  `MEMORY_MAX_PER_USER` (150) facts, so **pagination** may be needed — reuse the existing
  `QueuePageView` / `LyricsPageView` paginated-View pattern in `cogs/music.py`
  (`:122`, `:148`) rather than inventing one. (See Open Question 1.)
- **Confirmation UX specifics** (button labels, timeout) — planner discretion; follow the
  finite-timeout confirm-view pattern established by `/discover` (14-04) and `/jam
  suggest` (14-05), not a `setup_hook`-registered persistent view.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements (this phase)
- `.planning/ROADMAP.md` §"Phase 15: RAG Reach" — goal, 4 success criteria, deps.
- `.planning/REQUIREMENTS.md` — RAG-01, RAG-02, RAG-03, RAG-04 (+ Out of Scope table).

### Phase 11 foundation (the memory substrate — authoritative on mechanics)
- `.planning/phases/11-rag-long-term-memory/11-CONTEXT.md` — D-04 (occasional-payoff
  cadence, the principle D-01 narrows to ambient-only), D-06 (candidate-ammo-may-NOOP),
  and the "SQL owns numbers, semantic owns episodes" accuracy firewall.
- `.planning/research/SUMMARY.md` / `FEATURES.md` / `ARCHITECTURE.md` / `PITFALLS.md` —
  the flagship research; binding on recall/prompt-injection mechanics. Esp. Pitfall 8
  ("no memory beats a wrong memory") and the accuracy firewall.

### Surfaces already wired (verify + cadence-tune — D-01)
- `cogs/ai.py` — `/ask` recall (`:128–145`, invoker-scoped) and `/roast` recall
  (`:206–222`, **target**-scoped `str(target.id)`). Both gated on
  `MEMORY_CALLBACK_CHANCE` today; D-01 removes that gate here only.
- `cogs/events.py:128` (ambient roast) + `cogs/music.py:1272` (notable-event roast) —
  the ambient surfaces that **keep** the 0.35 gate (D-01). Regression targets: do not
  change their cadence.
- `personality/prompts.py::build_chat_prompt(..., memories=...)` — the backward-compatible
  injection seam; empty/None must render byte-identical (RAG-02 guarantee).

### New-surface anchors (RAG-03 / RAG-04)
- `services/memory.py::recall` (`:61`, optional `kind` filter, `user_id`-scoped) — the
  read primitive the `/memory` view uses; and its public API (`remember`/`sweep`).
- `database.py` `delete_user_memories` (`:1118–1142`, the T-11-04c per-id scoped-delete
  template) + `delete_expired_memories` (`:1171`) — the pattern the new
  `delete_all_user_memories(pool, user_id)` helper must mirror (bound `$N`, `WHERE
  user_id = $1`, never string interpolation).
- `cogs/library.py` `/jam` + `/playlist` `app_commands.Group` (`:460`, `:700`) — the
  slash-group + subcommand pattern for the `/memory` group.
- `cogs/music.py` `QueuePageView` (`:122`) / `LyricsPageView` (`:148`) — reuse for
  `/memory` view pagination if the user has many facts.
- `cogs/ai.py` (14-04 `/discover`) + `cogs/library.py` (14-05 `/jam suggest`) — the
  finite-timeout **confirm-view** pattern to reuse for the `/memory forget` confirmation.

### Config
- `config.py` §"Phase 11" `MEMORY_*` knobs (`:164–175`) — `MEMORY_SIMILARITY_FLOOR`
  (0.70), `MEMORY_CALLBACK_CHANCE` (0.35), `MEMORY_MAX_PER_USER` (150). No new knob is
  required for D-01/D-02/D-03; any `/memory` view page size lives alongside here.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `services/memory.py::recall(user_id, guild_id, query_text, kind=None)` — the read
  primitive for `/memory` view (call without a query anchor / with a broad anchor to list
  a user's facts; planner decides the retrieval shape for a *view* vs a *relevance* recall).
- `database.py::delete_user_memories` — the scoped-DELETE template (T-11-04c) to clone as
  `delete_all_user_memories(pool, user_id)`.
- `cogs/music.py` `QueuePageView` / `LyricsPageView` — paginated-embed View pattern for
  the `/memory` view.
- `/discover` (14-04) + `/jam suggest` (14-05) confirm-views — the propose/confirm pattern
  for the `/memory forget` confirmation gate.
- `cogs/library.py` `/jam` / `/playlist` groups — the `app_commands.Group` + subcommand
  scaffold for the `/memory` group.

### Established Patterns
- **Accuracy firewall (Critical Rule 12):** numbers from live SQL; memory supplies only
  the episode. `/memory` view shows the raw *episodic* facts verbatim — it never invents
  or reformats counts.
- **`user_id`-scoped writes/deletes with bound `$N` params** (T-11-04c) — the new delete
  helper must never string-interpolate and must scope `WHERE user_id = $1`.
- **Byte-identical `build_chat_prompt` fallback** — `memories or None` when nothing clears
  the floor (RAG-02); D-01 must preserve this.
- **Finite-timeout confirm-views** (14-04/14-05), NOT `setup_hook`-registered persistent
  views, for one-shot confirm actions.

### Integration Points
- Remove the `if random.random() < MEMORY_CALLBACK_CHANCE:` wrapper around recall in
  `cogs/ai.py` `/ask` (`:132`) and `/roast` (`:210`) only — leave `cogs/events.py:128`
  and `cogs/music.py:1272` untouched (D-01).
- New `delete_all_user_memories` in `database.py` (alongside the Phase 11 delete helpers).
- New `/memory` command group + view/forget subcommands (new cog or `cogs/ai.py`).
- New integration test: `remember → forget → recall == []` (Success Criterion 4).

</code_context>

<specifics>
## Specific Ideas

- **Feel target for `/memory` view:** Dex reluctantly showing you the file he's keeping —
  the *actual* dirt, verbatim, with a dry in-character intro ("fine, here's what i've got
  on you.") — so the transparency is real, not a flattering summary.
- **Feel target for `/memory forget`:** a clean, no-drama, irreversible "wipe it" — Dex
  acknowledges he now remembers nothing about you (a little wounded, in character), and it
  is genuinely, verifiably total. The escape hatch has to be *trustworthy* above all —
  Phase 16's proactive callbacks only earn the right to exist because this works.
- **The clean split that resolves the taste-erasure worry:** forget nukes the *memory
  store*, not the *play logs* — the taste brain regrows from `song_history` on its own.

</specifics>

<deferred>
## Deferred Ideas

- **Kind-aware / selective `/memory forget`** (e.g. "keep my taste, drop the roast ammo",
  or forget a specific listed item) — deliberately deferred out of Phase 15 in favor of
  clean nuke-all (D-03). Layers on top of nuke-all later without rework if real demand
  appears (mirrors Phase 11's "add later only if real misfires demand it" posture).
- **Owner/mod ability to forget *another* user's memory** — out of scope; `/memory forget`
  is strictly self-scoped. Privacy/abuse design would be its own thing.
- **Proactive unprompted memory callbacks + per-user opt-out** → Phase 16 (hard-blocked on
  RAG-04 shipping + being verified first).
- **Vision / multimodal roasting** → Phase 17.

None of the above are lost — each has a home in a later phase or the backlog.

</deferred>

<open_questions>
## Open Questions for the Planner (flag, don't guess)

1. **`/memory` view retrieval shape + pagination.** `recall()` is a *relevance* recall
   (ANN top-k against an anchor, with a similarity floor). A `/memory` *view* wants "show
   me everything you have" — that is a different query (list all of a user's rows, likely
   ordered by salience or recency, up to `MEMORY_MAX_PER_USER` = 150). Planner must decide:
   a new "list all facts for user" DB helper vs. driving `recall()` with a broad anchor +
   raised cap. Whichever, wire the existing `QueuePageView`/`LyricsPageView` pagination if
   the list can be long. Keep it read-only and ephemeral.

2. **Cadence-change regression coverage (D-01).** Removing the 0.35 gate from `/ask` /
   `/roast` must not disturb the ambient-roast recall tests (`cogs/events.py`,
   `cogs/music.py`). Confirm the existing mock-free/logic tests still assert the ambient
   surfaces keep the gate, and add/adjust an explicit-command test asserting recall now
   always fires when memory clears the floor (and still byte-identical when it doesn't).

</open_questions>

---

*Phase: 15-rag-reach*
*Context gathered: 2026-07-03*
