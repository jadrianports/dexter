# Project Research Summary

**Project:** Dexter ("Dex") — v1.3 "Taste Brain"
**Domain:** Additions to an existing, shipped, personality-driven Discord music+AI bot (semantic music memory, taste-aware recommendation, RAG-into-command-surfaces, proactive callbacks, vision/multimodal roasting)
**Researched:** 2026-07-02
**Confidence:** HIGH

## Executive Summary

v1.3 "Taste Brain" is not a new-systems milestone — it's a "wire it up in more places" milestone. All four research tracks (stack, features, architecture, pitfalls) independently converged on the same conclusion: everything the milestone needs already exists in the shipped v1.2 stack (`pgvector` on Neon, `MemoryService`, the dual Gemini rate limiters, `google-genai` 2.8.0, `discord.py` attachment handling). No new dependency, table, Postgres extension, rate limiter, or scheduling library is required. The five target features decompose cleanly onto existing seams: taste/listening facts become a new `kind` in the existing `user_memories` table (reusing `MemoryService.recall/remember/distill` completely unchanged); RAG-into-`/roast`/`/ask` is largely "already wired, just needs facts to flow through it"; proactive callbacks are a new `@tasks.loop` sibling of existing background loops gated by a new pure decision function; vision is a new, architecturally isolated cog reusing the shared 15 RPM chat limiter at priority 2.

The one genuinely new architectural discipline the milestone introduces is the **flavor-vs-numbers split** first established in Phase 11's "accuracy firewall": qualitative taste narrative (roast ammo, jam flavor, discovery blurbs) flows through the vector-memory pipe, while anything that *drives a decision* — auto-queue ranking, skip-weighted scoring, taste-graph adjacency — must come from live structured SQL over `song_history`/`user_artist_counts`, never from embedded text. This split recurs in every research file and should be treated as a hard constraint, not a style preference.

The dominant risk is not technical feasibility but **behavioral tuning and blast radius**, concentrated in two features: vision roasting (a genuinely new trust boundary — Gemini 2.5 defaults `safety_settings` to OFF, so an unprompted feature reacting to arbitrary user-uploaded images needs explicit, carefully-gated safety configuration, silent-not-fallback refusal handling, and conservative cadence to avoid quota starvation of `/ask`) and proactive callbacks (a genuinely new "the bot reaches into the past unprompted" surface that must anchor to active moments, fire rarer than existing ambient roasts, and ship alongside `/memory forget` as an escape hatch before it lands). Both risks are well-understood and mitigated by patterns this codebase already has proven — cadence-gating, priority-tiered rate limiting, silent degradation — the work is applying them correctly to two new, higher-stakes surfaces.

## Key Findings

### Recommended Stack

**No new dependencies.** `requirements.txt` already covers every v1.3 capability: `google-genai` 2.8.0 supports multimodal image input (`types.Part.from_bytes`) and safety configuration (`types.SafetySetting`/`HarmCategory`/`HarmBlockThreshold`) natively; `discord.py` `Attachment.read()`/`.content_type`/`.size` covers image ingestion with no Pillow/opencv needed; `pgvector` + `gemini-embedding-001` (already wired for v1.2 RAG) covers taste embeddings as just another memory `kind`; `asyncpg` SQL aggregation over existing tables covers taste-graph discovery (no `networkx`, no graph DB, no vector DB alternative — pgvector already won that argument in Phase 11); `asyncio` background-task patterns already used 4x in `bot.py` cover proactive callbacks (no APScheduler/celery).

**The one required change is a config/call-shape decision, not a library:** Gemini 2.5-series models default `safety_settings` to **OFF** when unspecified. Today's `chat()`/`generate_image()` never pass `safety_settings` (low-risk for trusted text input); the moment vision processes arbitrary user-uploaded images, this becomes a real gap that must be closed with explicit `HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE`-style settings on all four adjustable categories. Vision shares the existing 15 RPM chat limiter (a multimodal request counts as one request against RPM/RPD) — no second limiter needed.

### Expected Features

**Must have (table stakes):**
- New `taste_episode`-style memory kind, distilled + number-free like existing kinds — reuses `distill_and_remember()` end to end
- Auto-queue respects recent skips as a negative-signal prompt hint (SQL aggregation → text injected into existing Gemini auto-queue prompt, not a new subsystem)
- `recall()` wired into `/roast` and `/ask` (plumbing already kwarg-compatible since Phase 11)
- `/memory view` (ephemeral, paginated) + `/memory forget <id>`/`forget all` — required before shipping more memory-surfacing features, for trust
- Vision: explicit `safety_settings`, cadence-gated + designated-channel-only, silent decline on safety-block (no visible error, unlike `/imagine`'s direct-request refusal template), priority-2 on the shared limiter

**Should have (differentiators):**
- Skip-aware, session-scoped artist deprioritization in auto-queue (not permanent — tastes shift)
- `/taste`-style artist-adjacency discovery command (SQL co-occurrence + one-line Gemini narration)
- "Continue this jam" generative suggestion for `/jam` playlists (reuses existing auto-queue pipeline, capped rounds)
- `/roast @user` referencing one real remembered episode — the single highest "wow it remembers" moment in this milestone
- Proactive callbacks delivered in-personality as a dry aside, rarer than ambient-roast cadence, anchored to an active moment

**Defer / anti-features (explicitly avoid):**
- Real collaborative filtering / audio-feature embeddings / genre taxonomy — no data or user-base scale to justify it; Gemini-in-the-loop + SQL co-occurrence is already right-sized
- Continuous "radio mode" auto-queue with no stop condition — violates existing `AUTO_QUEUE_MAX_ROUNDS` discipline
- `/memory edit`, exposing raw similarity scores, cross-user recall scoping for `/roast`
- Proactive DMs, standing background "watch for the perfect moment" pollers, per-user opt-out preference systems in v1 (self-limiting cadence is the actual mitigation), cross-referencing multiple memories into one "recap"
- Persisting image-derived content into RAG memory in v1.3; long-term image storage
- Salience reinforcement, `/setavatar`, resuming the parked 24/7 deploy (explicitly out of scope per PROJECT.md)

### Architecture Approach

Five additions layer onto exactly the seams v1.2 already built, with zero new tables/extensions/limiters/schedulers. Taste memory extends `user_memories`/`MEMORY_SALIENCE_BASE_WEIGHTS` with new kinds, written by a new distillation pass over `song_history` (not the message buffer) — consumed two ways: qualitative flavor via the *unchanged* `MemoryService.recall()` (kind-agnostic already), and quantitative signal via *new* structured SQL aggregates (never embedded — the accuracy firewall). Taste-graph/recommendation logic gets its own pure `logic/taste.py` module (mirroring `logic/autoqueue.py`/`logic/roasts.py` conventions) plus a new `services/taste.py` orchestrator, because three consumers (auto-queue, discovery command, generative jams) would otherwise duplicate SQL+Gemini glue across cogs. RAG-into-`/roast`+`/ask` costs zero new plumbing — facts flow through the existing pipe once written. Proactive callbacks are a new `@tasks.loop` at module scope in `bot.py` (never cog-owned, matching every existing background loop), gated by a new pure `decide_proactive_callback()` sibling of `decide_ambient_roast`, piggybacking on the existing `idle_check` loneliness-detection state rather than building a second quiet-detector. Vision is a new, standalone `cogs/vision.py` (mirrors the precedent of `imagine.py` vs `ai.py` — image *understanding* is its own feature domain, not bolted onto `events.py::on_message`), with a new `GeminiService.describe_image()` sharing the existing rate limiter.

**Major components:**
1. `logic/taste.py` (pure, TDD) — artist affinity scoring, novelty filtering, discovery ranking
2. `services/taste.py` (`TasteService`) — orchestrates SQL + Gemini + optional `MemoryService.recall()` for auto-queue, discovery, and jams
3. `bot.py` new `@tasks.loop`s — `taste_distill_batch` (daily) and `proactive_callback` (10-15 min, gated on existing idle-loneliness state)
4. `cogs/vision.py` + `GeminiService.describe_image()` + `logic/vision.py` — isolated, safety-gated image-understanding surface
5. `cogs/memory.py` (or extension) — `/memory view`/`forget`, scoped hard to `interaction.user.id`

### Critical Pitfalls

1. **Vision safety refusal must be silent-skip, never a fallback template** — treating any Gemini refusal as "retry or fall back to a generic joke" defeats the safety gate entirely; this must be a distinct code branch from rate-limit/API-down handling, which correctly uses the guaranteed-fallback pattern.
2. **Vision is the only feature adding genuinely new load to the shared 15 RPM chat budget** — unthrottled reaction to every posted image will starve `/ask`. Mitigate with cadence-gate (probability + cooldown) + priority-2 routing + designated-channel-only + hard per-day vision-call cap, mirroring `MAX_IMAGES_PER_USER_PER_DAY`.
3. **Proactive callbacks are the first unprompted surface with no natural in-the-moment anchor** — reusing the ambient-roast cooldown dict as-is under-guards the one new dimension: "is right now a good moment." Anchor to active moments, cap per-user-per-day in addition to the probability roll, and ship `/memory forget` first as the escape hatch.
4. **Cross-user memory leakage risk grows with call-site count, not because the existing guard is weak** — `search_memories`'s `WHERE user_id` guard (T-11-03a) is sound today, but taste-graph/generative-jam features are explicitly multi-user/guild-scoped in a way `/ask`/ambient roasts aren't. Any accidental per-user `recall()` loop or omitted scope filter reintroduces the leak. Require an explicit multi-user-safe aggregate pattern (not a per-user loop) plus a regression test asserting scoped queries never cross `user_id`.
5. **Stale taste memories surfaced as current** — a "likes artist X" fact has a much shorter half-life than a milestone/personality fact; memory must inform but never decide (auto-queue ranking stays SQL-driven), and taste-kind decay/rerank parameters should be set deliberately rather than inherited unmodified from Phase 11's general-fact defaults.

## Implications for Roadmap

Based on research, suggested phase structure (continuing numbering at Phase 13):

### Phase 13: Semantic Music Memory (foundation)
**Rationale:** Every other feature reads from this; must ship first and run at least a day against real usage before consumers are built (mirrors the Phase 11 live-Neon-spike-before-retrieval precedent).
**Delivers:** New `taste_episode` (and optionally `taste_shift`) memory kind in `MEMORY_SALIENCE_BASE_WEIGHTS`; new structured `database.py` aggregate helper(s) for artist play/skip counts; new `taste_distill_batch` `@tasks.loop` reading `song_history`/`user_artist_counts` (never message buffer) into `distill_and_remember()`.
**Addresses:** Semantic music memory (target feature 1).
**Avoids:** Pitfall 5 (stale/contradicted memory) by deliberately setting taste-kind decay params up front rather than inheriting general-fact defaults.

### Phase 14: Smarter Music Brain
**Rationale:** First and second-through-third real consumers of the foundation; validates the whole taste pipeline end-to-end against well-understood existing code (`try_auto_queue`) before building new UI surfaces.
**Delivers:** `logic/taste.py` (pure, TDD: `compute_artist_affinity`, novelty filtering, ranking) → `services/taste.py` (`TasteService`, wired in `bot.py:_initialize_once`) → skip-aware auto-queue deprioritization inserted before `validate_youtube_match` → `/taste`-style discovery command → "continue this jam" generative suggestion for `/jam` playlists.
**Uses:** `song_history.was_skipped`, `user_artist_counts`, existing Gemini auto-queue prompt pipeline, `logic/autoqueue.py` validator (reused, not replaced).
**Avoids:** Pitfall 7 (filter-bubble convergence — reserve an exploration budget, don't purely exploit skip-avoidance; branch cold-start explicitly rather than falling through to bland server-average picks); Pitfall 10 (event-loop blocking — prefer SQL aggregation over in-Python clustering).

### Phase 15: RAG Reach (`/roast`, `/ask`, `/memory`)
**Rationale:** Mostly "verify it's landing well and tune weights," since `recall()` is already wired kwarg-compatible into both commands — cheapest phase in the milestone, and establishes the multi-user-safe scoping discipline that Phase 14's discovery/jam work and Phase 16 both need to inherit.
**Delivers:** `/roast @user` and `/ask` memory injection verified/tuned for the new taste kind (cap at one memory reference); `/memory view` (ephemeral, paginated) + `/memory forget <id>`/`forget all` with accurate scope-of-erasure messaging (does not cascade to derivative memories) and hard-delete confirmed.
**Addresses:** RAG reach (target feature 3) — the trust/escape-hatch prerequisite for Phase 16.
**Avoids:** Pitfall 4 (cross-user leak — establish the explicit multi-user-safe aggregate pattern + regression test here, reused by Phase 14); Pitfall 6 (`/memory forget` incomplete erasure — document scope accurately).

### Phase 16: Proactive Memory Callbacks
**Rationale:** Depends on Phase 13+15 having something worth surfacing and a working `/memory forget` escape hatch landed first — shipping a new "the bot brings up your past unprompted" surface before users can opt out of specific facts is a bad trust ordering.
**Delivers:** New `decide_proactive_callback()` pure function (TDD, sibling of `decide_ambient_roast`) → new `proactive_callback` `@tasks.loop` in `bot.py`, piggybacking on existing `idle_check` loneliness state, rarer cadence + longer per-user cooldown than ambient roasts, hard daily cap alongside the probability roll, silent skip on empty `recall()` result.
**Addresses:** Proactive callbacks (target feature 4).
**Avoids:** Pitfall 3 (creepy-callback risk — anchor to active moments only, never a cold timer/DM; conservative default cadence, tune from live feedback).

### Phase 17: Vision / Multimodal Roasting
**Rationale:** Architecturally independent of everything above (different Gemini call shape, no taste-memory dependency) but sequenced last deliberately — it is the highest-blast-radius new surface (unprompted content generation from arbitrary user-uploaded images) and benefits from the content-safety/cadence-gating discipline already proven out by Phase 16.
**Delivers:** `logic/vision.py` (`decide_vision_roast`, pure, TDD) → `GeminiService.describe_image()` with explicit `safety_settings` (`BLOCK_MEDIUM_AND_ABOVE` per adjustable category, never `BLOCK_NONE`) → new isolated `cogs/vision.py` filtering `message.attachments` by `content_type.startswith("image/")`, designated-channel-only, priority-2 on the shared 15 RPM limiter, silent decline (no fallback template) on any safety refusal, first-image-only cap on multi-image messages, synchronous fetch-at-receipt (CDN URLs expire).
**Addresses:** Vision/multimodal roasting (target feature 5, VIS-01/02).
**Avoids:** Pitfall 1 (content-safety/legal liability — application-level hard-rule prompt layer beyond Gemini's own filters, never treat refusal as retryable); Pitfall 2 (quota/privacy blowout — cadence gate + priority-2 + hard daily cap); Pitfall 8 (attachment edge cases — content-type allowlist, size ceiling, synchronous fetch, single-image cap).

### Phase Ordering Rationale

- **Foundation-before-consumers, structured-before-orchestration, low-risk-before-new-surfaces** — this ordering is independently confirmed by ARCHITECTURE.md's "Suggested Build Order" and FEATURES.md's "MVP Recommendation," which converge on the same sequence almost exactly.
- **Taste-graph and skip-aware auto-queue are SQL-first, not RAG-first** — they can ship even if the new memory kind's tuning slips, since they read `song_history`/`user_artist_counts` directly and only optionally enhance with semantic flavor.
- **`/memory forget` must land before proactive callbacks** — shipping more autonomous memory-surfacing behavior without a working delete path first is explicitly flagged as a bad trust ordering by both FEATURES.md and PITFALLS.md.
- **Vision is sequenced last for blast-radius reasons, not dependency reasons** — it could technically be built in parallel with the taste-brain track, but every research file independently recommends deferring it until the content-safety/cadence patterns are freshly proven by the proactive-callback work.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 17 (Vision):** exact free-tier RPD/TPM numbers are MEDIUM confidence (third-party trackers, not the account-gated AI Studio dashboard); tiling token-cost formula for large images is LOW confidence. Neither is load-bearing (RPM, not TPM, is the binding constraint at this bot's scale) but should be spot-verified against the live AI Studio dashboard before finalizing `MAX_VISION_IMAGE_BYTES`/cooldown config values.
- **Phase 16 (Proactive callbacks):** cadence/"creepy threshold" numbers are MEDIUM-LOW confidence — synthesized product-design reasoning, not citation-verified against Discord-specific case studies. Treat `PROACTIVE_CALLBACK_CHANCE`/`_COOLDOWN_SECONDS`/`_INTERVAL_SECONDS` as spike-tunable defaults, not settled values — plan to observe live and retune.

Phases with standard patterns (skip research-phase):
- **Phase 13 (Semantic memory foundation):** direct extension of already-shipped, well-documented Phase 11 `MemoryService` plumbing — kind-agnostic by design, zero code change needed in `services/memory.py`/`models/memory.py`.
- **Phase 14 (Smarter music brain):** SQL aggregation + existing Gemini auto-queue prompt pattern, both already proven in this codebase (`logic/skip_stats.py`/`/skips` is a direct analog).
- **Phase 15 (RAG reach):** plumbing already built kwarg-compatible in Phase 11; this is verification/tuning, not new architecture.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Context7-verified against the actually-installed `google-genai==2.8.0`; zero new dependencies needed, cross-confirmed by all four research files |
| Features | MEDIUM-HIGH | Grounded in shipped v1.2 infra + official Gemini safety docs; proactive-callback cadence norms are synthesized product reasoning (no Discord-specific case studies found), explicitly flagged LOW-MEDIUM within FEATURES.md |
| Architecture | HIGH | Grounded in direct reads of `bot.py`, `services/memory.py`, `services/gemini.py`, `cogs/*`, `database.py`, `logic/*`, `config.py`, plus Context7-verified multimodal API shape |
| Pitfalls | HIGH on rate-limiter/architecture mechanics; MEDIUM on vision token-cost/safety specifics; MEDIUM-LOW on creepy-callback thresholds (explicitly no formal research base for Discord bots specifically) |

**Overall confidence:** HIGH

### Gaps to Address

- **Exact taste memory salience/decay tier** (`taste_episode` weight, whether a distinct `taste_shift` kind is warranted) is a config-value judgment call flagged for requirements/roadmap, not resolved by this research — mirrors the `MAX_IMAGES_PER_USER_PER_DAY`-style precedent of deciding exact numbers during planning.
- **Proactive callback cadence constants** (`PROACTIVE_CALLBACK_CHANCE`, cooldown, interval) are directional starting points only (0.15-0.20 chance, 1-2hr cooldown, 10-15min poll suggested) — explicitly flagged as spike-tunable from live observation, not settled.
- **Whether to retrofit `safety_settings` onto the existing `chat()`/`generate_image()` calls** (`/ask`, `/imagine`) is a latent gap STACK.md surfaced but did not resolve — both currently rely on Gemini's OFF-by-default filtering for trusted text input. Flag as a small hardening task decision for requirements, not a v1.3 stack blocker.
- **Whether generative jams extend `cogs/library.py` (existing `/jam` home) or land in a new cog** is an open placement question noted in ARCHITECTURE.md's New Components table — resolve during Phase 14 planning.
- **Whether a distinct "pause proactive callbacks for me" toggle is needed separately from `/memory forget`** is explicitly flagged by PITFALLS.md as worth deciding before Phase 16, since forgetting a fact and opting out of the *surface* are different asks.

## Sources

### Primary (HIGH confidence)
- Context7 `/googleapis/python-genai` — `Part.from_bytes`, `SafetySetting`/`HarmCategory` signatures, verified against installed `google-genai==2.8.0`
- Context7 `/rapptz/discord.py` — `Attachment` API surface
- Direct codebase reads (this repo): `bot.py`, `config.py`, `services/gemini.py`, `services/memory.py`, `models/memory.py`, `database.py`, `cogs/ai.py`, `cogs/events.py`, `cogs/library.py`, `logic/autoqueue.py`, `logic/roasts.py`, `personality/prompts.py`, `requirements.txt`, `.planning/PROJECT.md`, `CLAUDE.md`
- ai.google.dev/gemini-api/docs/safety-settings — default-OFF-for-2.5/3-models finding, harm category list, CSAM/child-safety always-on

### Secondary (MEDIUM confidence)
- ai.google.dev/gemini-api/docs/image-understanding — supported MIME types, 20MB inline-data limit, token/tiling cost estimates
- ai.google.dev/gemini-api/docs/rate-limits — confirms tier-dependent limits, does not surface exact free-tier numbers
- WebSearch aggregation (multiple third-party trackers) — free-tier RPM/TPM/RPD figures, multimodal-counts-as-one-request confirmation

### Tertiary (LOW confidence)
- WebSearch: "Discord bot 'remembers you' proactive callback design pattern avoid spammy creepy" — no strong Discord-specific case studies found; proactive-callback cadence recommendations are synthesized from this bot's own existing cadence-gating conventions plus general chatbot-proactivity reasoning — validate empirically against live usage
- Tiling token-cost formula for very large images — single WebFetch summary, not cross-verified; not load-bearing at this bot's scale (RPM, not TPM, is binding)

---
*Research completed: 2026-07-02*
*Ready for roadmap: yes*
