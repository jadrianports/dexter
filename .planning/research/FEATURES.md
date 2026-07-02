# Feature Research: v1.3 "Taste Brain"

**Domain:** Personality-driven Discord music+AI bot — semantic music memory, taste-aware recommendation, RAG-powered social features, vision/multimodal roasting
**Researched:** 2026-07-02
**Confidence:** MEDIUM-HIGH (grounded in existing shipped v1.2 RAG infra + official Gemini safety docs; proactive-callback cadence norms are synthesized product-design reasoning, not citation-verified — flagged LOW where so)

> Supersedes the previous contents of this file, which covered Phase 11 (v1.2 RAG long-term memory research, 2026-06-26). That work is shipped; this file now covers the v1.3 milestone that builds on top of it.

## Answers to the Specific Questions

**(a) Music recommendation/taste-graph for a single small community — simplest approach that feels smart:**
Don't build a recommender. **Gemini-in-the-loop is already the correct architecture** — auto-queue since v1.0 sends recent-session history to Gemini and gets back suggestions; that pattern is right-sized for a single server with maybe a few dozen active listeners and a few thousand `song_history` rows. Pure embeddings-of-songs or collaborative filtering need either (1) a large user base for collaborative signal or (2) external music metadata (genre/audio features) this stack doesn't have — both are over-engineering for one Discord server. The one place raw **co-occurrence counting earns its keep** is the *taste-graph discovery command* (`/taste` or similar): a plain SQL self-join over `song_history`/`user_artist_counts` ("artists queued in the same session/day as artist X") gives an artist-adjacency graph that is 100% accurate (grounded in real plays, zero hallucination risk) and costs nothing — no embeddings, no Gemini call needed for the graph itself, only for the personality-flavored narration wrapping it. Auto-queue then gets *smarter*, not *different*: feed the existing Gemini prompt a skip-derived negative-signal hint ("avoid artists this user recently skipped: X, Y") computed by a `was_skipped` SQL aggregation — a prompt-input change, not a new subsystem.

**What makes auto-queue feel good vs. annoying:**
- Diversity — never queue the same artist twice in a row from auto-suggestions.
- Respecting explicit rejection — 2+ skips of the same artist in a session should deprioritize that artist for the rest of the session (not permanently; tastes and moods shift).
- A hard stop — `AUTO_QUEUE_MAX_ROUNDS` already caps runaway suggestion loops; keep that discipline for any new generative-jam variant.
- Transparency — auto-queued tracks are already labeled as such (`was_auto_queued`); keep doing this, it's why the "ignored" memory kind works and why users trust the feature.
- An easy out — `/skip` already exists; don't add friction to escaping a bad auto-queue run.
Annoying = repeating a just-skipped artist, ignoring skip signal entirely, or an auto-queue that never stops suggesting after the room has gone quiet.

**(b) How skip data should feed recommendation:** Purely as a *negative prompt signal*, not a scoring model. `was_skipped=true` rows aggregated per-user-per-artist over a recent window (e.g. last N days or last session) become "avoid" hints injected into the existing Gemini auto-queue prompt, and separately become the taste-graph's "cold" edges (artists that co-occur with skips, not just plays). No need for a skip-weighted embedding space or decay-weighted scoring function — that's ML sophistication a single-server bot doesn't need. `/skips` (Phase 12) already aggregates this at the SQL layer; reuse `logic/skip_stats.py` as the analog rather than building new stats plumbing.

**(c) Proactive/unprompted callbacks — timing/cadence that feels delightful not spammy/creepy:** (MEDIUM-LOW confidence — synthesized from Dexter's own existing cadence-gating conventions plus general chatbot-proactivity product-design reasoning; authoritative "how other Discord bots do this" case studies were not found in web search)
- **Piggyback on existing event hooks, don't invent a new poll.** Dexter already has cadence-gated triggers (voice join/leave 30%, late-night 50%, idle-loneliness single-shot). A proactive memory callback should attach to one of these existing touchpoints (or song-start) rather than run its own background scanner — cheaper, and avoids the "the bot is watching a timer for me" feeling that a bespoke poll implies.
- **Rarer than the existing ambient-roast cadence.** `MEMORY_CALLBACK_CHANCE = 0.35` already governs whether an *existing* roast surface injects a memory. A *new, unprompted* volunteer-a-memory surface needs its own lower probability plus a per-user cooldown longer than the 5-minute voice-roast cooldown — once-per-day-per-user order of magnitude is a reasonable starting anchor, tightened after live observation. Rarity is what makes a callback feel like a genuine "oh, it remembered" moment instead of a running commentary track.
- **Only fire adjacent to real user activity**, never in a vacuum — when the user just did something (posted, joined voice, queued a song), not a cold ping to an idle channel. "Proactive" here means unprompted *relative to a command*, not unprompted relative to presence — never DM, never @mention out of nowhere.
- **Specificity + brevity, not a data dump.** One memory, framed as an aside inside the existing personality voice (dry, deflecting), not a "here's what I know about you" reveal. The existing `last_surfaced_at` novelty penalty in `rerank()` already prevents replaying the same memory — keep leaning on it so callbacks don't go stale.
- **The personality is the anti-creepy mechanism.** A tracking-and-surfacing feature reads as surveillance in a neutral voice; it reads as banter in Dexter's sarcastic, self-aware, "yeah I noticed, so what" voice. This is a real asset already built — don't undercut it with an overly sincere or analytical callback tone.

**(d) `/memory` command UX conventions:** No single dominant convention was found for Discord specifically, but the "view your data / delete your data" pattern is consistent across chat-memory products in general: list view (paginated, ephemeral — memories are personal, must not post to the channel) + delete-by-id and delete-all. Recommend a slash command group: `/memory view` (paginated list, reuse the `/lyrics`/`/history` pagination pattern already in the codebase), `/memory forget <id>`, `/memory forget all`. Show the fact text, kind, and a relative "how long ago" — never raw similarity scores or embeddings (those are implementation detail, not user-facing). View-and-delete only; no edit (editing a memory is a data-integrity/misuse surface with no real user benefit — if it's wrong, delete and let the daily distill regenerate it naturally).

**(e) Vision roasting — what lands, when to react vs. stay silent, content-safety UX:**
- **What lands:** reacting to clearly-legible, unremarkable images (screenshots, memes, selfies, pets, food) in the bot's own dry voice — the same "accurate first, sarcastic second" rule as `/ask` applies: describe/react to what's actually visible, don't invent detail.
- **When to stay silent (not just decline politely — actually say nothing):** unclear/blurry/low-content images, anything the safety filter flags (`finish_reason == SAFETY` / `promptFeedback.blockReason` — see below), borderline-NSFW (skip rather than gamble on a bad take), and rapid-fire meme/reaction-image spam (a cadence gate handles this generically). Unprompted behavior in this codebase already degrades silently everywhere (memory recall, roast generation) — an unprompted vision reaction that can't safely fire should follow the same convention: no message at all, not a fallback apology. This is different from `/imagine`, which is a direct user request and therefore owes the user *some* response (the existing `IMAGE_REFUSAL_MESSAGES` template) — an unprompted reaction owes nobody a response.
- **Content-safety UX (verified against official Gemini docs via WebFetch):** the Gemini API's four adjustable harm categories (harassment, hate speech, sexually explicit, dangerous content) default to **`OFF`** on 2.5-series models — Dexter must explicitly set `safety_settings` (e.g. `BLOCK_MEDIUM_AND_ABOVE`) rather than relying on the default, since the default is permissive, not conservative. Detect a block via `Candidate.finishReason == "SAFETY"` or `response.promptFeedback.blockReason`, and on either, drop the reaction attempt entirely (silent decline, per above). Built-in child-safety protections are always active and cannot be adjusted, which is an additional safety floor, not something to configure. Never attempt to identify specific people in photos — describe generically only (privacy + hallucination risk: vision models confidently misidentify people).

## Feature Landscape by Category

### 1. Music Brain (Semantic Memory + Smarter Auto-Queue + Taste Graph + Generative Jams)

#### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| New `music_taste`/`listening` memory kind, distilled + number-free like existing kinds | v1.2 shipped 5 memory kinds (milestone, late_night, repeat_song, auto_queue_ignored, daily_batch); a taste-brain milestone with no listening-derived memory kind would be incoherent | LOW | Pure config + prompt addition — reuses `distill_and_remember()` end-to-end (services/memory.py); needs a new entry in `MEMORY_SALIENCE_BASE_WEIGHTS` and a write trigger (see below) |
| Auto-queue respects recent skips (negative signal) | Users already expect `/skip` to "count for something"; today skips only feed the `auto_queue_ignored` memory kind after the fact, not the next suggestion round | LOW-MEDIUM | SQL aggregation over `song_history.was_skipped` → text hint appended to the existing Gemini auto-queue prompt; no new subsystem |
| Taste-graph discovery command is grounded in real history, never hallucinated | `/skips` (Phase 12) set the precedent: SQL-driven stats with a Gemini narrative wrapper, not Gemini-invented numbers — violating that (a hallucinated "you love X" with no play history) breaks the accuracy-first rule (CLAUDE.md Critical Rule 5) | MEDIUM | New SQL co-occurrence query (self-join on `song_history`/`user_artist_counts` scoped by guild/session) — `logic/skip_stats.py` is the direct analog for the pure-logic aggregation layer |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Skip-aware auto-queue (artist deprioritization within a session) | Auto-queue currently ignores skip outcome entirely when picking the *next* round — closing that loop is the single highest-leverage "smarter DJ" change | LOW | Session-scoped, not permanent — a skipped artist tonight may be wanted tomorrow; don't persist deprioritization past the session |
| `/taste` (or similar) artist-adjacency discovery command | "You also listen to X when you queue Y" is a genuinely fun, shareable output for a community bot — and it's cheap (SQL only, Gemini used only for the one-line narration) | MEDIUM | Co-occurrence = artists appearing in the same session/day, weighted by frequency; Louvain-style clustering or true graph embeddings are unnecessary at this data scale — a simple top-N adjacency table is legible and sufficient |
| "Continue this jam" / suggest-additions to a `/jam` (Phase 12 per-server playlist) | Reuses the existing auto-queue Gemini-suggestion + `logic/autoqueue.py` token-set validator pipeline, aimed at a saved collection instead of the live queue — low marginal cost for a genuinely useful feature | LOW | On-demand (user-invoked command), capped rounds like existing auto-queue — do not make this a standing/continuous mode |

#### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Real collaborative filtering / matrix factorization over listeners | "Spotify does this, it must be better" | Needs a large user base for the collaborative signal to mean anything; a single Discord server has too few users and too sparse a play matrix — output would be noise dressed as intelligence | Gemini-in-the-loop (already the shipped pattern) + SQL co-occurrence for the graph command |
| Embedding-based song/audio similarity (BPM/key/timbre, audio fingerprinting) | Sounds like the "correct" ML way to do music similarity | Needs audio-analysis libraries and/or a metadata API not in the stack (yt-dlp gives title/duration, not audio features); real infra + cost for a single-server bot | Title/artist-level co-occurrence (already accurate for "adjacent taste") + Gemini's own music-domain knowledge in the existing suggestion prompt |
| Continuous "radio mode" that auto-queues indefinitely without a stop condition | Feels like a natural extension of auto-queue | Runs away on RPM budget, and an endless auto-DJ with no cap contradicts the existing `AUTO_QUEUE_MAX_ROUNDS` discipline that was deliberately added to prevent exactly this | Keep "continue this jam" a capped, on-demand, round-limited command like auto-queue |
| Genre taxonomy stored in the schema | Feels necessary for a "taste graph" | No genre metadata exists anywhere in the pipeline (yt-dlp doesn't reliably provide it); building/maintaining a taxonomy is a whole side project | Artist-only adjacency graph; if a genre-flavored narrative is wanted, let Gemini characterize it in prose at read-time (cheap, no storage, no accuracy claims) |

---

### 2. RAG Reach (`/roast`, `/ask`, `/memory`)

#### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| `recall()` wired into `/roast` and `/ask` | Ambient roasts already use memory; a milestone framed around RAG reach with the two flagship AI commands still memory-blind would be an obvious gap, and `build_chat_prompt(memories=...)` was already built kwarg-compatible for exactly this in Phase 11 | LOW | Plumbing already exists (11-PATTERNS.md documents the exact call site pattern for `/ask`); `/roast @user` needs recall scoped to the **target's** `user_id`, not the invoker's — a one-line but easy-to-get-backwards distinction |
| `/memory view` — ephemeral, paginated | Memories are personal; posting someone's tracked history/opinions into a shared channel is a privacy misstep independent of any specific convention | LOW-MEDIUM | `interaction.response.send_message(..., ephemeral=True)`; reuse `/lyrics`/`/history` pagination pattern |
| `/memory forget <id>` and `/memory forget all` | "View your data" without "delete your data" is half a feature and erodes trust in a bot that already tracks a lot (streaks, history, taste) | LOW-MEDIUM | New DB helper scoped `WHERE id = $1 AND user_id = $2` — must not allow deleting another user's memory by guessing an id |
| Recall failure degrades silently everywhere it's wired | Consistent with every existing memory touchpoint (`recall()` already returns `[]` on any error) | LOW | No new pattern — just don't special-case `/roast`/`/ask` to break this convention |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| `/memory` doubles as a debugging/trust surface | Lets the single-server owner (and any curious user) sanity-check *what* the bot actually remembers, which builds trust in an otherwise opaque background feature and helps catch bad distillations early | LOW | Show kind + fact + relative age; no similarity/salience internals — those are implementation detail, not user value |
| `/roast @user` referencing a real remembered episode | This is the single most "wow it actually remembers" moment available in this milestone, precisely because `/roast` is already the most personality-forward existing command | LOW (plumbing) / MEDIUM (prompt tuning) | Cap at one memory reference like the existing ambient-roast injection guidance ("use at most one, only if it genuinely lands") — don't let `/roast` become a memory dump |

#### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| `/memory edit` | Feels like a completeness nice-to-have next to view/forget | Data-integrity and misuse surface (a user could rewrite what the bot "remembers" about themselves or others) for near-zero real benefit | Delete + let the daily distill/remember pipeline regenerate a corrected fact naturally over time |
| Exposing raw similarity/salience/embedding data in `/memory view` | "More transparency is always better" | Meaningless to non-technical users, and leaks internal tuning constants that shouldn't be user-facing surface area | Human-readable fact + kind + relative time only |
| Recall scoped across all users for `/roast` (i.e., "what does everyone say about this person") | Would make `/roast @user` richer | Breaks the existing per-user ANN scoping (`WHERE user_id`) that Phase 11 deliberately built as a cross-user guard (T-11-03a) — this is a privacy boundary, not an oversight | Keep target-user-only scoping; richness comes from letting the daily batch distill more, not from widening the recall scope |

---

### 3. Proactive Callbacks

#### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Cadence-gated (probability + per-user cooldown), never guaranteed | Every existing unprompted behavior in this bot (voice roasts, late-night, idle-loneliness) is cadence-gated — an unthrottled proactive callback would be the first unprompted feature in the bot that ISN'T self-limiting, and would immediately feel different (worse) | LOW | Mirror `UNPROMPTED_ROAST_CHANCE` + per-user-cooldown pattern already in `cogs/events.py`; new config constants, no new architecture |
| Fires only in the designated channel | CLAUDE.md Critical Rule 9: "designated channel only — don't spam every channel" — this rule predates v1.3 and applies unchanged | LOW | Reuse `DEXTER_CHANNEL_ID` gate already used everywhere else |
| Attached to an existing event hook (voice join, song start, idle check), not a new standalone poll | Cheapest to build, and avoids introducing a background scanner whose sole job is "wait for the right moment to interrupt someone" — which is the exact shape of behavior that reads as creepy | LOW-MEDIUM | Extends an existing `@tasks.loop` or event handler rather than adding a new one |
| Silent when there's nothing worth surfacing | `recall()` already returns `[]` gracefully; a proactive callback with no qualifying memory should just not fire that cycle, same as everything else | LOW | No new fallback template needed — absence of a memory is a no-op, not an error |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Rarer cadence than existing ambient roasts (own probability + longer cooldown) | Rarity is the delight mechanism — a callback that fires as often as a voice-join roast stops feeling like "it remembered" and starts feeling like "it always talks about my past" | LOW | New config constants (e.g. `PROACTIVE_CALLBACK_CHANCE`, a per-user last-fired timestamp) — deliberately tuned lower/longer than existing roast cadence |
| Delivered in-voice/in-personality as an aside, not a standalone "memory alert" | Keeps the feature inside the bot's existing sarcastic-banter frame rather than introducing a new, more sincere/analytical tone that would break character and read as more surveillance-like | LOW | Reuse the existing roast-generation prompt path with the memory injected, not a bespoke "I remember when..." template |

#### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Proactive DMs | "More personal, more direct" | Unprompted DMs from a bot are the textbook definition of creepy/spammy in Discord bot etiquette, and users never opted into DM-level tracking-and-surfacing just by joining a server | Designated-channel-only, as every other unprompted behavior already does |
| A dedicated new background poll scanning "for the perfect moment" | Sounds more sophisticated/proactive | Extra infra for no real gain over hooking existing events, and a standing "always watching for a moment to strike" loop is itself the behavior pattern that feels invasive, independent of how rarely it actually fires | Attach to existing event hooks (voice join/leave, song start, idle check) |
| Per-user opt-out/preference toggle for callbacks in v1 | Feels considerate and "the right thing to do" | Real scope creep — new settings storage, new command, new UX for a single-server hobby bot; the self-limiting cadence (low probability + cooldown) is the actual mitigation, not a preference system | Ship with a deliberately conservative default cadence; only build an opt-out if live usage shows it's actually needed |
| Cross-referencing multiple memories into one "recap" callback | More data = more impressive | Turns a light aside into a data dump, which is the single fastest way to make "remembers you" feel like "surveils you" | One memory per callback, same cap discipline as the existing roast-injection guidance |

---

### 4. Vision / Multimodal Roasting

#### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Explicit `safety_settings` configured (not left at SDK default) | Gemini 2.5-series models default all four adjustable harm categories to `OFF` (verified via official docs) — an unprompted vision feature reacting to whatever gets posted in a community channel absolutely cannot run with filters off | LOW | `types.SafetySetting(category=..., threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE)` per category, passed in `GenerateContentConfig` |
| Cadence-gated, designated-channel-only, same as every other unprompted behavior | Reacting to every single image posted would be both an RPM-budget risk (shared 15 RPM budget, CLAUDE.md Critical Rule 1) and a spam risk | LOW | Reuse the existing emoji-reaction/roast cadence pattern in `cogs/events.py` |
| Silent decline on safety-blocked or low-confidence content — no visible error/apology | Every other unprompted surface in this bot degrades silently (memory recall, roast generation); a vision feature that posts "sorry, I can't react to that" every time it declines would itself become the annoying/conspicuous behavior, and worse, would broadcast "safety filter triggered" next to whatever image caused it | LOW | Check `finish_reason == "SAFETY"` / `promptFeedback.blockReason`; on either, or on rate-limit, just don't send a message — mirrors `memory.recall()`'s `[]`-on-error convention, distinct from `/imagine`'s visible `IMAGE_REFUSAL_MESSAGES` (that's a direct user request and owes a response; this doesn't) |
| Priority-2 (background) on the shared 15 RPM Gemini budget | CLAUDE.md Critical Rule 1: all AI features share one limiter, user commands (`/ask`, `/imagine`) must not starve | LOW | Same priority-tier discipline already used for embeddings/background memory writes — vision reactions must never block or delay a user-invoked command |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Reactions delivered in the existing dry/lowercase/one-emoji-max voice | Makes vision feel like a natural extension of the bot's established character rather than a bolted-on gimmick — this is the actual competitive/delight angle, not the vision capability itself | LOW (reuses `personality/prompts.py` conventions) | Same accuracy-first-sarcasm-second rule as text: describe what's actually in the image before being sarcastic about it |
| Occasional, unpredictable — not every image, not on a fixed schedule | Unpredictability is what makes each hit feel earned rather than mechanical | LOW | Pure function of the existing probability-gate pattern |

#### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Reacting to every image posted | "More reactive = more alive" | Burns shared 15 RPM budget fast, and constant reaction to every meme/screenshot becomes noise, not personality | Cadence-gate identically to every other unprompted behavior (~20-30% + per-user cooldown, tune from live observation) |
| A visible "I can't look at that" refusal message on unprompted images | Feels more transparent/helpful | Broadcasts "this image tripped the safety filter" next to the image in a shared channel — actively worse than silence, and inconsistent with how every other unprompted failure in this bot already behaves (silent) | Say nothing; only `/imagine`-style direct requests get a visible refusal, because only direct requests owe the user a response |
| Attempting to identify specific people in photos | Feels like a fun "personalized" roast angle | Vision models confidently misidentify people; combined with the accuracy-first rule and privacy concerns, this is a hallucination and reputational risk with no real upside | React to generic visible content (objects, scenes, vibe, text-in-image) — never claim to recognize who's pictured |
| Persisting image-derived reactions into RAG long-term memory in v1 | Seems consistent with "everything becomes a memory" | Opens a second sensitive-content surface that needs its own PII/safety review (Phase 11's `is_sensitive()`/`contains_number()` gates were built and tuned for text banter, not image content) — safer to ship vision as ephemeral reactions first and revisit memory-worthiness later once the safety story for image-derived facts has been thought through | Keep vision reactions one-off/ephemeral in v1.3; treat "should image reactions feed memory" as an explicit open question for a later milestone, not a default |
| Downloading and long-term-storing posted images for later analysis | Sounds useful for "look back at what was posted" | New storage surface, new privacy/retention question, and no feature in this milestone actually needs it — the reaction is meant to be in-the-moment | Analyze the attachment at message-time only (URL or in-memory bytes), never persist |

## Feature Dependencies

```
Semantic Music Memory (new "music_taste" kind)
    └──requires──> v1.2 RAG infra: pgvector, MemoryService.distill/remember/recall (SHIPPED, Phase 11)
    └──requires──> song_history / user_artist_counts data (SHIPPED, Phase 1/4)

Skip-aware auto-queue
    └──requires──> song_history.was_skipped (SHIPPED)
    └──enhances──> existing Gemini auto-queue prompt (SHIPPED, cogs/music.py + services/gemini.py)

Taste-graph discovery command (`/taste`)
    └──requires──> song_history / user_artist_counts co-occurrence query (NEW SQL, analog: logic/skip_stats.py)
    └──enhances──> Semantic Music Memory (optional: narrate the graph using recalled taste episodes)

"Continue this jam" / suggest-additions
    └──requires──> existing auto-queue Gemini-suggestion pipeline + logic/autoqueue.py validator (SHIPPED)
    └──requires──> /jam per-server playlists (SHIPPED, Phase 12)

RAG into /roast, /ask
    └──requires──> v1.2 RAG infra: MemoryService.recall(), build_chat_prompt(memories=) (SHIPPED, Phase 11)

/memory view + forget
    └──requires──> v1.2 RAG infra: user_memories table (SHIPPED)
    └──requires──> new DB helpers: list_user_memories (paginated), delete_memory(id, user_id) (NEW)

Proactive memory callbacks
    └──requires──> RAG into /roast pathway's recall() + roast-generation prompt (reuses same call shape)
    └──requires──> existing event hooks: voice join/leave, song-start, idle-loneliness check (SHIPPED, cogs/events.py)
    └──enhances──> Semantic Music Memory (more memory kinds = richer callback pool)

Vision / multimodal roasting
    └──requires──> existing Gemini chat service + shared 15 RPM limiter (SHIPPED, services/gemini.py)
    └──requires──> existing on_message event hook + cadence-gate pattern (SHIPPED, cogs/events.py)
    └──independent of──> RAG memory (ships standalone; do NOT wire image content into user_memories in v1.3 — see Anti-Features)
```

### Dependency Notes

- **Everything in this milestone sits on top of Phase 11's RAG infra** (pgvector, `MemoryService`, priority-tiered embedding limiter) — zero new infrastructure is needed for Music Brain, RAG Reach, or Proactive Callbacks. This is a "wire it up more places + add data-driven inputs" milestone, not a new-systems milestone.
- **Taste-graph discovery and skip-aware auto-queue are SQL-first, not RAG-first** — they read `song_history`/`user_artist_counts` directly. Semantic memory *enhances* the narrative layer on top but is not a hard dependency for the graph or the skip-signal itself. This matters for phase ordering: the SQL-driven pieces can ship even if the new memory kind slips.
- **Vision roasting is architecturally independent** of everything else in this milestone (different Gemini call shape — multimodal input, not text/embeddings) and shares only the 15 RPM budget and the existing cadence-gate/event-hook pattern. It could be sequenced as its own phase without blocking or being blocked by the RAG-reach work.
- **`/memory` forget is a hard prerequisite for user trust in the rest of the milestone** — shipping *more* memory-surfacing features (RAG reach, proactive callbacks) without a working delete path first would be a bad ordering; recommend it lands early, alongside or just after the new memory kind.

## MVP Recommendation

### Highest leverage, lowest complexity (do first)

- Skip-aware auto-queue negative-signal hint — reuses 100% existing plumbing, closes an obvious existing gap
- `recall()` wired into `/roast` and `/ask` — plumbing already built kwarg-compatible in Phase 11, this is mostly wiring + prompt-injection cap discipline
- `/memory view` + `/memory forget` — required for trust before shipping more memory-surfacing features

### Second wave (builds on the above)

- New `music_taste` memory kind + write trigger (session-end or daily-batch aggregation)
- `/taste` artist-adjacency discovery command (SQL co-occurrence + Gemini narration wrapper)
- Proactive memory callbacks (needs the memory kind + recall wiring above to have something worth surfacing)

### Independent track (can parallelize)

- Vision/multimodal roasting — no dependency on the RAG-reach work; gate on safety-settings correctness and cadence discipline, not on anything else in this milestone

### Explicitly defer (per PROJECT.md, already out of scope)

- Salience reinforcement (→ v1.4)
- Any per-user preference/opt-out system for proactive callbacks
- Persisting image-derived content into RAG memory
- Genre taxonomy / audio-feature-based recommendation

## Free-Tier / RPM Impact Summary

| Feature | Gemini calls added | Budget | Priority tier |
|---------|--------------------|--------|----------------|
| Semantic music memory (new kind) | 1 distill + 1 embed per write event | Separate 60 RPM embed limiter (existing) | 2 (background) |
| Skip-aware auto-queue | 0 new calls — same auto-queue prompt, richer input text | Shared 15 RPM chat budget (existing) | 2 (background) |
| `/taste` discovery command | 1 chat call per invocation (narration only) | Shared 15 RPM chat budget | 1 (user command) |
| "Continue this jam" | Same as existing auto-queue (capped rounds) | Shared 15 RPM chat budget | 1 (user command) |
| RAG into `/roast`/`/ask` | 1 embed (query) per invocation — recall already this shape elsewhere | Separate 60 RPM embed limiter | 1 (user command) |
| `/memory view`/`forget` | 0 — pure DB reads/deletes | n/a | n/a |
| Proactive callbacks | 1 embed (recall) + reuses existing roast-generation chat call | Both limiters, low frequency by design | 2 (background) |
| Vision roasting | 1 multimodal chat call per triggered reaction | Shared 15 RPM chat budget — new consumer of this specific limiter | 2 (background) |

**Net risk:** vision roasting is the only feature adding a genuinely new class of load to the *shared* 15 RPM chat budget (the others either add embed-limiter load, which is separate and headroom-rich at 60 RPM, or add zero/negligible chat-budget load). Cadence-gate vision aggressively and keep it priority-2 so it can never contend with `/ask`/`/imagine`.

## Sources

- `.planning/phases/11-rag-long-term-memory/11-PATTERNS.md` — shipped RAG plumbing, call-site patterns for `/ask`, priority tiers, `build_chat_prompt(memories=)` signature (HIGH confidence, direct codebase read)
- `services/memory.py` — shipped `recall()`/`remember()`/`distill()`/`sweep()` implementation (HIGH confidence, direct codebase read)
- `logic/autoqueue.py` — shipped token-set auto-queue validation, analog for any new suggestion-consuming logic (HIGH confidence, direct codebase read)
- `config.py` — existing cadence constants (`UNPROMPTED_ROAST_CHANCE`, `MEMORY_CALLBACK_CHANCE`, `EMBED_RPM_LIMIT`, memory tuning constants) used as anchors for new-feature cadence recommendations (HIGH confidence, direct codebase read)
- [Safety settings | Gemini API | Google AI for Developers](https://ai.google.dev/gemini-api/docs/safety-settings) — harm categories, default-OFF threshold on 2.5-series models, `finishReason`/`promptFeedback.blockReason` detection (HIGH confidence, official docs, WebFetch-verified 2026-07-02)
- WebSearch: "simple music recommendation co-occurrence artist adjacency small community bot" — general confirmation that co-occurrence/adjacency graphs are a legitimate lightweight alternative to full collaborative filtering (MEDIUM confidence, general ML-community consensus, no single authoritative source)
- WebSearch: "Discord bot 'remembers you' proactive callback design pattern avoid spammy creepy" — did not surface strong Discord-specific case studies; proactive-callback cadence recommendations in this document are synthesized from Dexter's own existing cadence-gating conventions plus general chatbot-proactivity product-design reasoning (LOW-MEDIUM confidence, flagged explicitly — validate empirically against live usage rather than treating cadence numbers as settled)
- `CLAUDE.md` — Critical Rules 1 (shared 15 RPM), 7 (one emoji max), 9 (designated channel only), personality rules — used as hard constraints throughout (HIGH confidence, project source of truth)

---
*Feature research for: Dexter v1.3 "Taste Brain"*
*Researched: 2026-07-02*
