# Phase 16: Proactive Memory Callbacks - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning

> ⚠️ **Session note:** The user launched `/gsd:discuss-phase 16`, was presented the
> domain boundary + the four gray areas, and **selected all four** for discussion. The
> user then stepped away before answering the first area's question (60s AFK). Following
> the **explicit Phase 14/15 precedent** ("decided on the user's behalf" — see
> `15-CONTEXT.md` session note), **all four decisions below (D-01…D-04) are Claude's
> conservative, requirement-anchored recommendations, adopted on the user's behalf.**
> They are deliberately the safest reading of PROACT-01/02 and the anti-creepy discipline,
> and every one is tunable. **The user should skim the decisions and revise before
> `/gsd-plan-phase 16` if any feel wrong.** All numeric values remain
> Claude's-/planner's-discretion (mirrors Phase 11/13/14/15).

<domain>
## Phase Boundary

Dexter gets a **third, rarest speaking cadence**: it occasionally *volunteers* a recalled
memory **unprompted**, anchored to an **active moment in the designated channel** — never a
cold background poll, never a DM. This is the first surface where Dex speaks without a
command or a voice event triggering it, so the **anti-creepy discipline is the deliverable**:
sarcasm as the disarming voice, rarity below the ambient rate, an additive daily cap, and a
per-user opt-out that is distinct from deleting the underlying memory.

**Hard dependency (satisfied):** Phase 15 `/memory forget` (RAG-04) ships as a verified
hard-delete — the trust escape hatch that had to exist *before* an autonomous
memory-surfacing surface. Do not reorder.

**In scope:**
- A proactive-callback surface that fires off a real active moment (D-01) in the designated
  channel, recalls the active user's memory, and volunteers a sarcastic callback (D-04).
- Cadence discipline: a probability roll **strictly rarer** than the 0.30–0.35 ambient
  rate, **plus** an additive **per-user daily cap** (D-02) — both must pass to fire.
- A per-user opt-out control (`/memory callbacks off|on`, D-03) that pauses proactive
  callbacks **without** touching stored memories — distinct from `/memory forget`.
- A pure `logic/` gate function (mirroring `logic/roasts.py::decide_ambient_roast`) that the
  new glue dispatches on (planner discretion on exact shape; strongly indicated below).

**Out of scope (belongs to later phases / permanent anti-features):**
- Vision / multimodal roasting → **Phase 17** (built on this phase's freshly-proven
  cadence/safety discipline).
- Any polling loop or DM delivery for callbacks — the "bot is watching me" failure mode;
  **permanently out** (REQUIREMENTS.md Out of Scope). Callbacks anchor to activity only.
- Salience reinforcement / recall-frequency decay tuning → v1.4 (MEM-R1).
- Embedding any SQL-known number — accuracy firewall, permanent.
- New memory `kind`, write path, table beyond the one opt-out flag, dependency, or limiter.

</domain>

<decisions>
## Implementation Decisions

### Active-moment anchor (PROACT-01) — what triggers a callback

- **D-01 (Claude recommendation, adopted on user's behalf): Chat message only.** A proactive
  callback is evaluated in the **`on_message` path** (`cogs/events.py:348`) when a **non-bot
  user posts in the designated channel** — the cleanest "they are actively here right now"
  signal, which the requirement's "active moment, never a cold poll" language demands. The
  recall target is the **message author** (their own memory, scoped to `str(author.id)`),
  and the callback is anchored to that message (D-04). **Voice-join is deliberately NOT a
  trigger** — voice-join already fires *ambient* roasts (`on_voice_state_update`, 0.30 gate),
  and stacking a second surface there would double-fire and muddy the cadence math. Keeping
  the proactive surface on `on_message` cleanly separates the three cadences (ambient-voice,
  ambient-notable-event, proactive-chat). *(Rejected: chat+voice — overlap/double-fire risk;
  chat-only-after-absence — better timing but needs per-user last-seen tracking and narrows
  firing so far it rarely triggers, over-engineering for v1.3.)*
  **Recommendation — revise if you want voice-join or return-from-absence as the anchor.**

### Rarity & daily cap (PROACT-01) — the anti-creepy cadence

- **D-02 (Claude recommendation, adopted on user's behalf): probability roll strictly below
  ambient, AND an additive PER-USER daily cap; both must pass.** Firing logic on a qualifying
  message, in order (short-circuit, cheapest gate first):
  1. **Opt-out check** (D-03) — skip immediately if the author paused callbacks.
  2. **Chance roll** — a new `PROACTIVE_CALLBACK_CHANCE` knob **strictly less than**
     `MEMORY_CALLBACK_CHANCE` (0.35) / `UNPROMPTED_ROAST_CHANCE` (0.30). Claude's suggested
     starting value **≈ 0.08–0.12** (planner/numeric discretion, tunable).
  3. **Per-user daily cap** — the **additive bound** PROACT-01 requires, keyed **per user
     per calendar day** (the meaningful anti-creepy limit: one individual can't be
     repeatedly singled out even on a lucky streak of rolls). Suggested cap **1/day per
     user** (tunable, `PROACTIVE_CALLBACK_DAILY_CAP`).
  4. **Recall floor** — only fire if `recall()` actually returns a memory clearing
     `MEMORY_SIMILARITY_FLOOR` (0.70). No memory → silently skip (Pitfall 8: "no memory
     beats a wrong memory"). This is what makes it *volunteer a real detail*, not fire blank.
  **Cap scope is PER-USER, not per-guild** — a per-guild cap would let one chatty user soak
  the whole server's budget or let the bot pile onto whoever happens to be talking; per-user
  is the correct privacy/annoyance bound. Counter storage is **planner discretion** — an
  in-memory `{user_id: (date, count)}` dict reset at day rollover is sufficient (a cap reset
  across a restart is harmless — rarer-is-fine, and proactive callbacks carry no durability
  requirement). Reuse the day-rollover convention already in `bot.py` daily loops if
  convenient. *(Rejected: per-guild cap — wrong bound; cap-before-roll — the roll should
  gate first so the cap is a ceiling on an already-rare event, matching "additive ON TOP OF
  the probability roll".)*
  **Recommendation — revise the scope (per-user vs per-guild) or the rough magnitudes.**

### Opt-out control (PROACT-02) — pause, distinct from forget

- **D-03 (Claude recommendation, adopted on user's behalf): a `/memory callbacks` toggle
  subcommand, indefinite on/off, stored as a boolean column on `user_profiles`, default
  opted-IN.** Add `callbacks` (or `pause`) as a **third subcommand under the existing
  `/memory` `app_commands.Group`** (`cogs/memory.py`, Phase 15) — the natural home, since
  proactive callbacks *are* a memory-surface behavior and the user already goes there to
  `view`/`forget`. Semantics: an **indefinite toggle** ("pause callbacks for me" until the
  user turns it back on), **not a timed snooze** — simpler, clearer, and matches PROACT-02's
  "pause callbacks for me" wording; a snooze adds expiry-tracking complexity for no asked-for
  benefit. **Default = opted-in** (callbacks ON) — PROACT-02 frames it as "a user can opt
  *out*", so the default state is on. **Storage:** a new boolean column on `user_profiles`
  (e.g. `proactive_opt_out BOOLEAN DEFAULT false`) via `ALTER TABLE ... ADD COLUMN IF NOT
  EXISTS` in `SCHEMA_SQL` — mirrors the Phase 8 `total_errors` additive-column pattern; **no
  new table**. **Crucially distinct from `/memory forget`:** the opt-out flips a flag and
  touches **zero** memory rows — the user's stored memories (and taste brain) stay fully
  intact; they've only silenced the *unprompted* surface. Ephemeral confirmation, in-character
  ("fine, i'll keep my mouth shut. your memories are still here though."). *(Rejected: timed
  snooze — unnecessary expiry complexity; separate `/callbacks` top-level command — worse
  discoverability than grouping under the memory surface it controls; new table — overkill
  for one boolean.)*
  **Recommendation — revise if you want a timed snooze, a different command surface, or
  opt-in-by-default.**

### Callback voice & shape (PROACT-01) — the anti-creepy mechanism itself

- **D-04 (Claude recommendation, adopted on user's behalf): a Gemini-framed sarcastic
  callback reusing the ambient recall→prompt→priority-2 path, posted as a REPLY to the
  triggering message, with `AllowedMentions.none()` and a guaranteed template fallback.**
  - **Gemini-framed, not verbatim** — the sarcastic voice is *the* anti-creepy mechanism
    (PROACT-01 / REQUIREMENTS.md). A raw verbatim fact ("you played X 40 times") reads as
    surveillance; a dry Dex line about it reads as a bit. **Reuse the existing
    `_generate_ambient_roast` machinery** (`cogs/events.py:87-172`): recall the author's
    memory → feed `build_chat_prompt(..., memories=...)` → priority-2 Gemini → enforce
    lowercase/length → template fallback on rate-limit/error. Do **not** invent a second
    recall path.
  - **Reply to the triggering message** (not a standalone drive-by post) so the callback is
    *visibly anchored* to the active moment — reinforcing "responding to you being here,"
    not "watching you." (Planner discretion on `message.reply` vs channel-send-with-context.)
  - **`AllowedMentions.none()`** — reference the user by display name, never ping. Mirrors
    every other ambient send (`cogs/events.py`) and keeps the surface low-aggression.
  - **Accuracy firewall preserved** — the callback references the episodic memory; any hard
    number still comes from live SQL, never embedded text.
  **Recommendation — revise if you want verbatim callbacks, standalone posts, or actual
  @mentions.**

### Claude's / Planner's Discretion (do NOT re-ask the user)

- **Pure-logic gate seam** — strongly indicated: a new `logic/proactive.py` with a
  keyword-only, `random`/`datetime`/`discord`-free gate function (e.g.
  `should_fire_proactive_callback(*, opted_out, chance_roll, chance, daily_count, daily_cap)
  -> bool`) mirroring `logic/roasts.py::decide_ambient_roast` (Phase 10 seam convention,
  D-02). The `on_message` glue computes the rolls/counts and dispatches on the result; the
  recall-floor check stays in glue (it's async I/O). Lock it under mock-free tests.
- **Exact numeric knob values** — `PROACTIVE_CALLBACK_CHANCE`, `PROACTIVE_CALLBACK_DAILY_CAP`
  (and any per-user cooldown if the planner wants belt-and-suspenders on top of the daily
  cap). Follow the Phase 11/13/14/15 discretion-on-numbers precedent.
- **Daily-counter storage mechanism** — in-memory dict vs reusing an existing daily-stats
  structure; either is fine (durability not required, D-02).
- **Cog placement of the trigger glue** — fold into `EventsCog.on_message` (alongside
  `_handle_message_reactions`) vs a small dedicated method; lean toward reusing `EventsCog`
  since the recall/roast helper already lives there.
- **Opt-out flag read path** — a small `database.py` getter/setter for `proactive_opt_out`
  (mirroring existing `user_profiles` helpers); wire the read into the `on_message` gate.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements (this phase)
- `.planning/ROADMAP.md` §"Phase 16: Proactive Memory Callbacks" — goal, 3 success criteria,
  the Phase 15 hard-dependency note.
- `.planning/REQUIREMENTS.md` — PROACT-01, PROACT-02 (+ the Out of Scope table: "Proactive
  callbacks via polling loop or DM" is a permanent anti-feature).

### The ambient-roast machinery to reuse (recall → Gemini → fallback)
- `cogs/events.py:87-172` — `_generate_ambient_roast`: the exact recall→`build_chat_prompt`
  (memories=…)→priority-2 Gemini→lowercase/length-enforce→template-fallback path D-04 reuses.
- `cogs/events.py:124-139` — the `MEMORY_CALLBACK_CHANCE`-gated ambient recall block; the
  proactive gate is a **rarer sibling**, not a modification of this. Regression target: the
  ambient 0.35 cadence must stay unchanged (Phase 15 D-01).
- `cogs/events.py:348-364` — `on_message`: the anchor point (D-01) where the proactive gate
  is evaluated; feeds `message_buffer` + `_handle_message_reactions` today.
- `cogs/events.py:44-83` — `_get_ambient_channel` / designated-channel resolution
  (`config.DEXTER_CHANNEL_ID`) — the proactive gate must confirm the message is in the
  designated channel before firing.

### Pure-logic seam (the pattern the new gate mirrors)
- `logic/roasts.py` — `decide_ambient_roast` + `cooldown_elapsed`: keyword-only,
  clock/`random`-injected, mock-free (Phase 10 D-01/D-02/D-03). `logic/proactive.py` follows
  this exactly.
- `tests/test_roast_logic.py` — the mock-free test convention to mirror for the new gate.
- `tests/test_ambient_recall_cadence.py` — the Phase 15 regression lock asserting ambient
  surfaces keep the `MEMORY_CALLBACK_CHANCE` gate; must stay green (proactive is additive).

### Memory read primitive + opt-out storage
- `services/memory.py::recall(user_id, guild_id, query_text, kind=None)` — the read the gate
  calls for the message author; returns [] below the floor (silent-skip path, D-02 step 4).
- `database.py` `user_profiles` helpers (e.g. `get_user_summary`, the profile
  upsert/getter pattern) — clone for the `proactive_opt_out` getter/setter (D-03).
- `database.py` `SCHEMA_SQL` — where the `ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS
  proactive_opt_out …` goes (mirrors the Phase 8 `total_errors` additive column; see CLAUDE.md
  Database Schema §Phase 8).

### The opt-out command home
- `cogs/memory.py` — the `/memory` `app_commands.Group` (`view` + `forget` today); D-03 adds
  a `callbacks`/`pause` toggle subcommand here. Header docstring documents the self-scoped
  (`str(interaction.user.id)`-only) security convention the new subcommand must follow.

### Config
- `config.py:160-193` §"Phase 11" `MEMORY_*` knobs — `MEMORY_CALLBACK_CHANCE` (0.35),
  `MEMORY_SIMILARITY_FLOOR` (0.70). New `PROACTIVE_CALLBACK_*` knobs live alongside; the
  chance MUST be set strictly below 0.30–0.35.
- `config.py` §"Phase 3" `UNPROMPTED_ROAST_CHANCE` (0.30), `AMBIENT_ROAST_CEILING_SECONDS` —
  the ambient rates the proactive chance must undercut.

### Prior-phase context (mechanics + cadence philosophy)
- `.planning/phases/15-rag-reach/15-CONTEXT.md` — D-01 (which surfaces keep the gate;
  proactive is the new rarer one), and the "decided on user's behalf" precedent this session
  follows.
- `.planning/phases/11-rag-long-term-memory/11-CONTEXT.md` — D-04 (occasional-payoff cadence,
  "rarity hits harder"), D-06 (injected memory is candidate ammo the model may NOOP), the
  accuracy firewall.
- `.planning/research/PITFALLS.md` — Pitfall 8 ("no memory beats a wrong memory" → the
  recall-floor silent-skip in D-02 step 4).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `cogs/events.py::_generate_ambient_roast` — the whole recall→Gemini→fallback pipeline;
  D-04 reuses it wholesale rather than writing a new callback generator.
- `services/memory.py::recall` — the author-scoped read; returns [] under the floor (the
  natural silent-skip).
- `cogs/memory.py` `/memory` group — drop-in home for the `callbacks` opt-out subcommand.
- `logic/roasts.py` `decide_ambient_roast` — the pure-gate template for `logic/proactive.py`.
- `user_profiles` table + its helpers — the store for the one opt-out boolean (no new table).

### Established Patterns
- **Three separate cadences** — voice-ambient (0.30), notable-event ambient (0.35),
  now proactive-chat (< 0.30, + per-user daily cap). Keep them independent; don't merge gates.
- **`logic/` pure seam** (Phase 10) — nondeterminism computed in glue, passed as primitives;
  gate is mock-free-tested.
- **Gemini-first with guaranteed template fallback** — never let a rate limit/API error
  block or crash a callback (personality is Gemini-first, fallback always).
- **`AllowedMentions.none()` on every ambient/unprompted send** — reference by name, no ping.
- **Additive `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`** (Phase 8 `total_errors`) — the
  opt-out column pattern; `SCHEMA_SQL` is idempotent.
- **Accuracy firewall** — episode from memory, numbers from live SQL, always.

### Integration Points
- New gate evaluated inside `EventsCog.on_message` (`cogs/events.py:348`) — after the
  bot-author guard, gated on designated-channel + opt-out + chance + daily-cap + recall-floor.
- New `logic/proactive.py` pure gate + `tests/` mock-free lock.
- New `PROACTIVE_CALLBACK_*` config knobs (chance < ambient, per-user daily cap).
- New `proactive_opt_out` column on `user_profiles` + getter/setter in `database.py`.
- New `callbacks`/`pause` subcommand in the `cogs/memory.py` `/memory` group.
- Regression: `tests/test_ambient_recall_cadence.py` + ambient roast paths stay byte-identical.

</code_context>

<specifics>
## Specific Ideas

- **Feel target for a proactive callback:** Dex, mid-conversation, dryly bringing up
  something he remembers about you — like a friend with a long memory and a sharp tongue, not
  a system that logs you. It lands *because* it's rare and *because* it's a joke. If it ever
  reads as "the bot is surveilling me," the design has failed — that's why it's Gemini-framed,
  reply-anchored, capped, and mutable.
- **The opt-out is a promise, not a delete:** "pause callbacks for me" must be honored
  instantly and completely, but it leaves the memories intact — a user who's just tired of
  being called out can silence the surface without nuking the taste brain. Distinct control,
  distinct from `/memory forget` (which stays the total escape hatch).
- **Rarity is a feature, not a bug:** a proactive callback that fires on ~8% of qualifying
  messages, capped at 1/user/day, will feel like a treat when it hits. Do not tune it up to
  "engaging" — under-firing is the safe failure mode.

</specifics>

<deferred>
## Deferred Ideas

- **Voice-join / return-from-absence as an additional proactive anchor** — D-01 scopes to
  chat messages to keep cadences clean; could be revisited if the chat anchor proves too rare
  in practice (would need per-user last-seen tracking).
- **Timed snooze ("pause for 24h") instead of an indefinite toggle** — D-03 chose the simpler
  indefinite toggle; a snooze can layer on later if users ask for it.
- **Per-guild proactive budget / rate shaping** — D-02 uses a per-user cap as the correct
  bound; a server-wide ceiling could be added later if a large guild ever feels noisy.
- **Salience reinforcement so frequently-recalled memories surface differently** → v1.4
  (MEM-R1), already deferred at the milestone level.
- **Vision / multimodal roasting** → Phase 17 (sequenced last; builds on this phase's proven
  cadence/safety discipline).

None of the above are lost — each has a home in a later phase or the backlog.

</deferred>

---

*Phase: 16-proactive-memory-callbacks*
*Context gathered: 2026-07-03*
