# Phase 17: Vision / Multimodal Roasting - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning

> ⚠️ **Session note:** The user launched `/gsd:discuss-phase 17`, was presented the domain
> boundary + the four gray areas, and **selected all four** for discussion. The user then
> stepped away (60s AFK) before answering the batched decision question. Following the
> **explicit Phase 14/15/16 precedent** ("decided on the user's behalf" — see
> `16-CONTEXT.md` session note), **all four decisions below (D-01…D-04) are Claude's
> conservative, requirement-anchored recommendations, adopted on the user's behalf.** They
> are deliberately the safest reading of VIS-01/02/03 and the anti-blast-radius discipline,
> and every one is tunable. **The user should skim the decisions and revise before
> `/gsd-plan-phase 17` if any feel wrong.** All numeric values remain
> Claude's-/planner's-discretion (mirrors Phase 11/13/14/15/16).

<domain>
## Phase Boundary

Dexter gets a **fourth unprompted cadence** — the highest-blast-radius surface in v1.3. It
occasionally **reacts to / roasts an image posted in the designated channel** via
`gemini-2.5-flash` vision input (`types.Part.from_bytes`), gated by chance + per-user
cooldown + **priority-2** on the shared 15 RPM limiter. Because this surface accepts
arbitrary user-uploaded pixels, **safety and cadence discipline are the deliverable** — a
two-layer safety model (explicit `safety_settings` **plus** an app-level hard rule), a
size/mime guard **before download**, and a **silent skip** on any safety block (no visible
refusal, never the generic rate-limit/API-down template). Sequenced last, deliberately,
built on the freshly-proven Phase 16 cadence/opt-out machinery.

**In scope:**
- An image-reaction surface evaluated in the `on_message` path (`cogs/events.py`), fired off
  an **image attachment** in the designated channel (D-02), gated by a new chance knob +
  per-user cooldown (D-04), calling Gemini vision at **priority-2**.
- A **before-download** guard: reject any attachment whose `content_type` is not in the mime
  allowlist or whose `size` exceeds `MAX_VISION_IMAGE_BYTES`, using Discord's attachment
  metadata (no bytes fetched) (VIS-01, D-02/D-03).
- **Two-layer safety** (VIS-02): explicit `safety_settings` on the vision call **plus** an
  app-level hard-rule layer (mime/size gate + a personality conduct clause in the vision
  prompt). A safety **block → silent skip** (return nothing; never the generic template
  fallback used for rate-limit/API-down).
- **Consistent `safety_settings`** across all user-influenced Gemini calls: retrofit `/ask`
  + `/imagine` alongside the vision call (D-01, VIS-03).
- A pure `logic/` gate seam (mirroring `logic/proactive.py::should_fire_proactive_callback`)
  the `on_message` glue dispatches on, locked under mock-free tests.
- Honor the existing **Phase 16 proactive opt-out** as the shared "unprompted-surface"
  silence (D-03) — a user who paused callbacks is also spared vision roasts.

**Out of scope (belongs to later phases / permanent anti-features):**
- **Vision reactions feeding RAG memory** — explicitly out of v1.3 (MEM-R2; needs its own
  safety-gate design first). The vision roast is fire-and-forget: no `remember()` write.
- **Pasted image URLs / embeds** as a trigger — arbitrary URL fetch = SSRF surface + defeats
  the pre-download size guard (D-02). Attachments only.
- Any polling loop or DM delivery — the "bot is watching me" failure mode; permanently out
  (inherited from the Phase 16 anti-creepy discipline). Reactions anchor to a posted image.
- New dependency, new table, new limiter, new memory `kind`, or a manual-avatar code path.

</domain>

<decisions>
## Implementation Decisions

### Safety-settings scope (VIS-03) — where explicit `safety_settings` are applied

- **D-01 (Claude recommendation, adopted on user's behalf): retrofit ALL THREE
  user-influenced surfaces — the vision call AND `/ask` + `/imagine`.** VIS-03 asks for
  `safety_settings` "applied **consistently** to Gemini calls that can receive
  user-influenced content," and Gemini 2.5 **defaults safety OFF**, so `/ask` and `/imagine`
  are unguarded today. Do it once, in a **shared helper** (`services/gemini.py`), threaded
  into every `generate_content` config. **Threshold differs by surface, deliberately:**
  - **Vision** (unprompted reaction to arbitrary user uploads) uses a **real BLOCK
    threshold** — a block yields a silent skip (D-03 / VIS-02). This is the surface that
    must actually refuse.
  - **`/ask` + `/imagine`** get **explicit but permissive** thresholds (e.g. block only the
    most severe categories) so Dex's existing edgy/roasty behavior is **not regressed** — the
    win here is *explicit, auditable* settings replacing an implicit off-default, not clamping
    the personality. Exact `HarmBlockThreshold` per category is planner discretion; the
    principle is: vision blocks for real, text/image-gen stay permissive-but-explicit.
  *(Rejected: vision-only — leaves the known `/ask`+`/imagine` gap open, and VIS-03 explicitly
  frames consistency as the goal; vision+`/imagine`-only — arbitrary split, `/ask` still takes
  user-influenced content.)*
  **Recommendation — revise if you want vision-only scope, or want `/ask`/`/imagine` clamped
  harder rather than kept permissive.**

### Trigger surface (VIS-01) — which images fire, and multi-image handling

- **D-02 (Claude recommendation, adopted on user's behalf): image ATTACHMENTS only; on a
  multi-image message, roast the FIRST valid image.** Evaluate in `on_message` (designated
  channel, non-bot author — the guards already present at `cogs/events.py:377-402`) over
  `message.attachments`, selecting attachments whose `content_type` starts with `image/` and
  is in the allowlist. **Discord exposes `attachment.content_type` and `attachment.size`
  without downloading**, which is exactly what VIS-01's "size guard and mime-type check
  **before download**" requires — the guard is a pure metadata check, and only a passing
  attachment is fetched (via `attachment.read()`) into `types.Part.from_bytes`. **Multiple
  images → pick the first valid one** (one roast per message keeps the cadence math clean and
  the priority-2 budget bounded). **Pasted image URLs / embeds are excluded** — fetching
  arbitrary URLs is an SSRF surface and gives no pre-download size, breaking the VIS-01 guard.
  *(Rejected: attachments + URLs — SSRF + no pre-download size; batch-aware — muddies cadence
  accounting and multiplies the vision-call cost for marginal benefit.)*
  **Recommendation — revise if you want pasted-URL support or batch roasting.**

### App-level hard-rule layer (VIS-02) — the layer beside `safety_settings`

- **D-03 (Claude recommendation, adopted on user's behalf): the hard rule = structural gate
  + a personality conduct clause, and it honors the shared Phase 16 opt-out.** VIS-02 wants
  `safety_settings` **plus** an app-level hard rule — the app-level layer is code we own, not
  the model:
  1. **Structural gate (pre-Gemini, hard reject → silent skip):** `content_type` must be in a
     mime allowlist (`image/png`, `image/jpeg`, `image/webp`, `image/gif` — planner may trim);
     `size` ≤ `MAX_VISION_IMAGE_BYTES`. Fails → never call Gemini.
  2. **Conduct clause (in the vision system prompt):** instruct Dex to roast the image's
     **content / vibe / subject matter**, and to **never** comment on a real person's face,
     body, weight, or perceived identity; if the image is primarily a person, keep it about
     the scene, not their appearance. This is the personality-level guardrail that keeps an
     edgy image roast from becoming a personal-appearance attack — the failure mode most
     likely to blow up socially.
  3. **Model-level `safety_settings`** (D-01) catch genuinely harmful/policy content; **any
     block → silent skip** (VIS-02): return nothing, do not `.reply`, do **not** route through
     the generic rate-limit/API-down template.
  4. **Shared opt-out:** a user who ran `/memory callbacks off` (Phase 16 `proactive_opt_out`)
     is **also** spared vision roasts — one "stop the unprompted stuff" control covers every
     unprompted surface. No new opt-out flag/column/subcommand for v1.3.
  *(Rejected: structural-gate-only — leans entirely on Gemini safety to avoid appearance
  roasting, the exact thing a dry app-level rule should prevent; dedicated vision opt-out —
  finer control but a second flag/column/subcommand users must discover, over-engineering when
  the Phase 16 opt-out already means "hush the unprompted surfaces".)*
  **Recommendation — revise if you want a separate vision opt-out, or a different conduct line
  (e.g. allow appearance roasts).**

### Reaction shape & cadence (VIS-01) — how the roast is delivered

- **D-04 (Claude recommendation, adopted on user's behalf): a Gemini-framed TEXT reply,
  reusing the Phase 16 reply-anchored path, gated by its own chance + per-user cooldown.**
  - **Text reply, not emoji** — VIS-01 says "reacts to / **roasts**"; the deliverable is a
    dry Dex line about the image. Post it as a **reply to the triggering message** with
    `AllowedMentions.none()` (visibly anchored to the image, no ping), lowercase/length
    enforced, **Gemini-first with a guaranteed template fallback** on rate-limit/API error —
    the exact `_generate_ambient_roast`-style pipeline (`cogs/events.py:87-172`), extended to
    pass an image `Part`. **Exception:** a *safety block* is **not** a fallback case — it is a
    silent skip (D-03 / VIS-02). Fallback templates cover transport failures only.
  - **Own cadence knobs:** a new `VISION_ROAST_CHANCE` (rarer; planner picks — suggested
    ≈ 0.10–0.15, tunable) + a per-user `VISION_ROAST_COOLDOWN_SECONDS`, mirroring the ambient
    per-user cooldown dict (`self._roast_cooldowns` at `cogs/events.py:34`). Keep this cadence
    **independent** of the ambient/proactive gates — a fourth distinct surface, not a merge.
  - **Priority-2** on the shared 15 RPM `_RateLimiter` (VIS-01) — background/unprompted, must
    yield to user commands and fall back (not block) on a priority-2 timeout.
  - **Pure-logic gate:** a `logic/vision.py` (or an added fn in an existing `logic/` module)
    `should_fire_vision_roast(*, chance_roll, chance, cooldown_elapsed, opted_out, ...) -> bool`,
    keyword-only, `random`/`datetime`/`discord`-free, mirroring
    `logic/proactive.py::should_fire_proactive_callback` (Phase 10/16 seam convention). Glue
    computes rolls/cooldowns/opt-out and dispatches on the result; the size/mime/attachment
    I/O stays in glue.
  *(Rejected: emoji-only — underdelivers on "roasts"; emoji + text — noisier surface for no
  requirement benefit.)*
  **Recommendation — revise if you want an emoji reaction alongside/instead, or a shared
  cadence with the ambient roasts.**

### Claude's / Planner's Discretion (do NOT re-ask the user)

- **Exact numeric knobs** — `MAX_VISION_IMAGE_BYTES`, `VISION_ROAST_CHANCE`,
  `VISION_ROAST_COOLDOWN_SECONDS`, the mime allowlist contents, and the per-category
  `HarmBlockThreshold` values for each of the three surfaces. Follow the Phase 11/13/14/15/16
  discretion-on-numbers precedent (chance strictly below the ambient 0.30/0.35 cadences).
- **`safety_settings` helper shape** — a module-level constant list vs. a builder that takes a
  per-surface threshold; either is fine so long as all three `generate_content` configs thread
  it and the vision surface gets the real-block threshold.
- **How a safety block is detected** — `response.prompt_feedback.block_reason`,
  `candidate.finish_reason == SAFETY`, and/or an empty-parts response; the planner picks the
  robust check. All map to "return None → glue silently skips."
- **Cog placement of the trigger glue** — fold into `EventsCog.on_message` (alongside the
  existing reaction + proactive-callback dispatch) vs. a small dedicated `_maybe_fire_vision_roast`
  method; lean toward a dedicated method mirroring `_maybe_fire_proactive_callback`.
- **Vision system prompt** — whether to reuse `build_chat_prompt` with an added image part or
  write a small dedicated vision prompt builder in `personality/prompts.py`; either, as long as
  the conduct clause (D-03 step 2) is present.
- **Daily-cap-vs-cooldown** — D-04 specifies a per-user cooldown; the planner may add a
  per-user/day cap too (belt-and-suspenders, mirroring Phase 16) if cheap.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements (this phase)
- `.planning/ROADMAP.md` §"Phase 17: Vision / Multimodal Roasting" — goal + 4 success
  criteria + the "sequenced last for blast radius" note.
- `.planning/REQUIREMENTS.md` — VIS-01, VIS-02, VIS-03 (+ the Out of Scope table: "Vision
  reactions feeding memory / manual avatar via code" is deferred to v2; MEM-R2 out of v1.3).

### The Gemini service (where the vision call + `safety_settings` retrofit land)
- `services/gemini.py:146-207` — `chat()`: the `generate_content` + `GenerateContentConfig`
  pattern; D-01 threads `safety_settings` into this config.
- `services/gemini.py:209-248` — `generate_image()`: the `/imagine` call; D-01 retrofits
  `safety_settings` here too; also the `response.candidates[0].content.parts` / `inline_data`
  extraction pattern the vision-response handling mirrors.
- `services/gemini.py:35-108` — the `_RateLimiter` with priority tiers; VIS-01's priority-2
  requirement rides this (a priority-2 timeout raises `GeminiRateLimitError` → template
  fallback for transport, silent-skip for safety).
- `services/gemini.py` `GeminiRateLimitError` / `GeminiAPIError` — the exceptions the vision
  glue distinguishes from a *safety block* (which is NOT an exception → silent skip).

### The ambient/proactive machinery to reuse (recall/roast → Gemini → fallback)
- `cogs/events.py:87-172` — `_generate_ambient_roast`: the recall→`build_chat_prompt`→
  priority-2 Gemini→lowercase/length-enforce→template-fallback pipeline D-04 extends with an
  image `Part`.
- `cogs/events.py:377-402` — `on_message`: the anchor point; already guards non-bot author +
  designated channel + `message.guild is not None`. The vision gate slots in beside the
  proactive-callback dispatch (line 395-402).
- `cogs/events.py:406-...` — `_maybe_fire_proactive_callback`: the structural template for a
  `_maybe_fire_vision_roast` method (opt-out read → pure gate → recall/generate → reply).
- `cogs/events.py:34` — `self._roast_cooldowns` per-user cooldown dict; the per-user vision
  cooldown mirrors it.
- `cogs/events.py:52-93` — `_get_ambient_channel` / designated-channel resolution
  (`config.DEXTER_CHANNEL_ID`).

### Pure-logic seam (the pattern the new gate mirrors)
- `logic/proactive.py::should_fire_proactive_callback` — keyword-only, `random`/`datetime`/
  `discord`-free gate; `logic/vision.py::should_fire_vision_roast` follows this exactly.
- `logic/roasts.py::decide_ambient_roast` + `cooldown_elapsed` — the original Phase 10 seam
  convention + cooldown helper the vision cooldown can reuse.
- `tests/test_roast_logic.py` — the mock-free test convention to mirror for the new gate.

### Opt-out (shared with Phase 16)
- `database.py::get_proactive_opt_out` / `set_proactive_opt_out` — the Phase 16
  `user_profiles.proactive_opt_out` read D-03 reuses to also silence vision (no new column).
- `cogs/memory.py` `/memory callbacks on|off` — the existing opt-out control; D-03 does NOT
  add a vision-specific one.

### Config
- `config.py:37-45` — `GEMINI_MODEL` (`gemini-2.5-flash`, the vision model), `IMAGEN_MODEL`,
  `IMAGINE_COOLDOWN_SECONDS`, `MAX_IMAGES_PER_USER_PER_DAY` (the daily-cap pattern to mirror).
- `config.py:61-64` — `UNPROMPTED_ROAST_CHANCE` (0.30) — the ambient rate `VISION_ROAST_CHANCE`
  must stay strictly below.
- `config.py:231` — `PROACTIVE_CALLBACK_CHANCE` (0.10) — the sibling rarer cadence knob; new
  `VISION_ROAST_*` knobs live alongside.

### Prior-phase context (cadence + safety discipline this phase inherits)
- `.planning/phases/16-proactive-memory-callbacks/16-CONTEXT.md` — the anti-creepy cadence
  philosophy, the reply-anchored + `AllowedMentions.none()` send pattern, the opt-out this
  phase reuses, and the "decided on user's behalf" precedent this session follows.
- `.planning/phases/11-rag-long-term-memory/11-CONTEXT.md` — priority-2 background-call
  discipline, the "no output beats a wrong output → silent skip" instinct.
- `.planning/research/PITFALLS.md` — vision-last sequencing rationale (blast radius).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `cogs/events.py::_generate_ambient_roast` — recall/roast→Gemini→fallback pipeline; extend
  with an image `Part` rather than writing a new generator.
- `cogs/events.py::_maybe_fire_proactive_callback` — structural template for the vision glue
  (opt-out read → pure gate → generate → reply-anchored send).
- `services/gemini.py::chat` / `generate_image` — the `generate_content`+config call sites for
  the `safety_settings` retrofit and the model for the vision call.
- `database.get_proactive_opt_out` — the shared unprompted-surface opt-out (no new flag).
- `logic/proactive.py` / `logic/roasts.py` — the pure-gate templates for `logic/vision.py`.
- `MAX_IMAGES_PER_USER_PER_DAY` / `_roast_cooldowns` — the daily-cap + per-user-cooldown
  patterns to mirror for vision cadence.

### Established Patterns
- **Distinct unprompted cadences** — voice-ambient (0.30), notable-event ambient (0.35),
  proactive-chat (0.10 + daily cap), now vision (new chance + per-user cooldown). Keep them
  independent; do not merge gates.
- **`logic/` pure seam** (Phase 10) — nondeterminism computed in glue, passed as primitives;
  gate is mock-free-tested.
- **Gemini-first with guaranteed template fallback** — but a *safety block* is a silent skip,
  NOT a fallback (VIS-02 — the one place fallback must not fire).
- **`AllowedMentions.none()` + reply-anchored** on every unprompted send.
- **Priority tiers on the shared 15 RPM limiter** — unprompted = priority-2, must yield/fall
  back rather than starve user commands.
- **Before-download metadata guard** — Discord `attachment.content_type` + `attachment.size`
  are available pre-fetch; the mime/size check is a pure metadata gate (VIS-01).

### Integration Points
- New vision gate + `_maybe_fire_vision_roast` in `EventsCog.on_message` (`cogs/events.py`),
  beside the proactive-callback dispatch.
- New `logic/vision.py` pure gate + `tests/` mock-free lock.
- `safety_settings` retrofit across all three `generate_content` sites in `services/gemini.py`.
- New `VISION_ROAST_*` + `MAX_VISION_IMAGE_BYTES` + mime-allowlist config knobs.
- Reuse `database.get_proactive_opt_out` (no schema change) + `_roast_cooldowns`-style dict.
- Regression: the ambient (0.35) + proactive (0.10) cadence tests + `/ask`/`/imagine` behavior
  must stay intact after the `safety_settings` retrofit (permissive thresholds → no regression).

</code_context>

<specifics>
## Specific Ideas

- **Feel target:** Dex glancing at an image someone dropped and firing off one dry line about
  it — rare enough to be a treat, never a pile-on, and never about the person's looks. If it
  ever reads as "the bot is judging my body" or "the bot reacts to everything I post," the
  design has failed — that's why it's chance+cooldown-gated, conduct-clamped, opt-out-able,
  and content-not-appearance focused.
- **Silent skip is sacred:** a safety-blocked image roast must vanish with zero trace — no
  "i can't look at that," no rate-limit template, no reaction. The absence IS the correct
  output (VIS-02).
- **The retrofit is a hardening win, not a personality change:** adding explicit
  `safety_settings` to `/ask`+`/imagine` replaces an implicit off-default with an auditable
  one; thresholds stay permissive so nothing users currently get from Dex regresses.
- **Rarity is a feature:** under-firing is the safe failure mode for the milestone's
  highest-blast-radius surface. Do not tune it up to "engaging."

</specifics>

<deferred>
## Deferred Ideas

- **Vision reactions feeding RAG memory** → v2 (MEM-R2) — needs its own safety-gate design
  before an image-derived fact touches the memory store. Explicitly out of v1.3.
- **Pasted image URLs / embeds as a trigger** — D-02 scopes to attachments for the
  SSRF/pre-download-size reasons; could be revisited with a hardened URL fetcher later.
- **A dedicated vision opt-out** distinct from the Phase 16 proactive opt-out — D-03 reuses
  the shared unprompted-surface control; a finer-grained flag can layer on if users ask.
- **Emoji reaction on images** (alongside/instead of the text roast) — D-04 chose text;
  an emoji layer could be added cheaply later.
- **Batch/multi-image roasting** — D-02 roasts the first valid image; whole-batch commentary
  could come later if the single-image surface proves too sparse.

None of the above are lost — each has a home in a later milestone or the backlog.

</deferred>

---

*Phase: 17-vision-multimodal-roasting*
*Context gathered: 2026-07-03*
