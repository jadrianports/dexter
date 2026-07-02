# Pitfalls Research

**Domain:** Adding semantic music memory, taste-aware auto-queue, RAG-into-`/roast`/`/ask`, proactive callbacks, and vision/multimodal roasting to an existing discord.py + `google-genai` + Neon/`pgvector` personality bot on the **free Gemini Developer API tier** (Dexter v1.3 "Taste Brain")
**Researched:** 2026-07-02
**Confidence:** HIGH on rate-limiter/architecture mechanics (verified against `services/gemini.py`, `services/memory.py`, `cogs/events.py`, `config.py`); MEDIUM on Gemini vision token-cost and safety-filter specifics (verified via official docs, but free-tier numeric RPD/TPM values are account-tier-dependent and not published as stable constants — confirm in AI Studio before locking config); MEDIUM-LOW on "creepy callback" thresholds (no formal research exists for Discord bots specifically — synthesized from social-computing UX conventions + this bot's own existing cadence-gate pattern).

> Feature areas below map to the five v1.3 target features in PROJECT.md. Exact phase numbers are TBD by the roadmap (continuing at Phase 13); pitfalls reference the **feature area**, and the roadmap should assign phase numbers preserving the dependency order already implied by PROJECT.md (semantic memory foundation → music brain + RAG reach → proactive callbacks → vision, which is architecturally independent and should stay isolated).

---

## Critical Pitfalls

### Pitfall 1: Vision roasting becomes a content-safety / legal liability, not just a UX bug

**What goes wrong:**
Dex is pointed at `gemini-2.5-flash` with an image attachment and asked to produce a sarcastic caption. Three distinct failure modes compound:
1. A user posts CSAM, gore, or another Trust & Safety violation. Gemini's **non-configurable** core-harm classifier (child safety, CSAM, PII) blocks generation regardless of `HarmBlockThreshold` settings — but if the bot's error handling treats *any* refusal as "try again" or "fall back to a generic joke," it can end up commenting on the image anyway via a template fallback, or retry-loop against a request that will never succeed (burning RPM budget on a request guaranteed to fail).
2. A user posts a legal-but-sensitive image (a medical photo, an ID card, a screenshot containing another person's private info, a photo of a minor who isn't the poster) that clears Gemini's *adjustable* filters (harassment / hate speech / sexually explicit / dangerous content — these are threshold-tunable, not hard blocks) but is still inappropriate to publicly roast in a shared Discord channel.
3. The roast itself — even of a "safe" image — can be wrong in a way that's actively harmful: commenting on someone's body, misgendering someone in a photo, or reading medical/disability equipment as a joke prop.

**Why it happens:**
The existing `/imagine` path already treats "refused" as a single bucket (`generate_image` returns `None` on refusal — `services/gemini.py:209-248`, `GeminiRefusalError` is *defined* but never raised anywhere in the codebase today). That pattern is fine for a bot-generated image (worst case: no image, mildly funny "I refuse to draw this" line). It is **not** fine for vision, where the risky content already exists (a real photo of a real person) and the harm is in Dex *commenting* on it, not in generating it. Developers porting the existing refusal-as-None pattern to vision will silently under-guard: no image reaches the model → fine; image reaches the model, model complies, output is inappropriate → the existing pattern has no gate for this because it was never a risk in the pure-text/pure-generation case.

**How to avoid:**
- Set explicit `HarmBlockThreshold` on all four adjustable categories for the vision call — do NOT use `BLOCK_NONE` (confirmed via official docs: `BLOCK_NONE` only disables the *probabilistic* filter for that category; it does not disable the hard-coded CSAM/child-safety block, so there is no upside to loosening it here, only downside).
- Treat `finish_reason == SAFETY` / a refusal response as **"do not roast, silently skip"** — never fall back to a generic personality line when the *reason* generation was blocked was a safety trigger. A fallback line defeats the purpose of the block. This is a new branch distinct from "Gemini is rate-limited" or "Gemini is down," where the guaranteed-template-fallback pattern correctly applies (Critical Rule: "Gemini-first personality output with guaranteed template fallback" is about *availability*, not about *safety refusals* — do not conflate the two).
- Add an **application-level opt-out list of content categories Dex will not comment on even if Gemini allows it**: no comments on bodies/appearance, no comments implying a photo shows a minor, no medical/disability-equipment jokes. Bake this into the vision system prompt as hard rules, not just rely on the model's own judgment (mirrors the existing "never sacrifice accuracy for personality" prompt-engineering discipline already used for `/ask`).
- Log every vision-safety refusal to the error channel at DEBUG (not the roast/error channel that pings the owner) so patterns can be reviewed without creating a "the bot is monitoring what gets blocked" chilling effect in-channel.
- Never retry a safety-refused request — refusal is not a transient failure, retrying wastes RPM budget on a request that structurally cannot succeed.

**Warning signs:**
- A vision roast fires on an image that should have been blocked (spot-check refusal logs weekly during rollout).
- The vision cog has a single `try/except` around the whole Gemini call with one fallback branch (red flag: safety and rate-limit/API-down are being treated identically).
- No system-prompt section enumerating "never comment on X."

**Phase to address:** Vision / multimodal roasting (last v1.3 phase, per PROJECT.md ordering) — VIS-02 is explicitly the content-safety guardrail requirement; this pitfall should shape its acceptance criteria, not be discovered after ship.

---

### Pitfall 2: Vision roasting on every posted image is a free-tier quota and privacy time bomb

**What goes wrong:**
The obvious implementation — `on_message` sees any attachment with an image content-type, sends it to Gemini, posts a caption — has two compounding costs: (1) each call consumes a shared-budget RPM slot *and* a non-trivial token allowance (Gemini tiles images into 258-token blocks per ~768×768 region; a typical phone-camera screenshot posted to Discord easily lands at 1,000–1,600+ input tokens per call, before the reply itself), and (2) it reacts to *every* image regardless of whether the user wanted commentary — memes, screenshots of a friend's private message, someone's ID for a form, a photo shared for a completely unrelated reason. On an active server, image-posting frequency can exceed message frequency that currently drives `/ask`/auto-queue, so an unthrottled vision path can dominate the shared 15 RPM budget and starve `/ask` and music auto-queue — the exact starvation failure the priority-tier rate limiter was built to prevent for embeddings (Critical Rule 1), except vision has no separate limiter to protect it from or be protected by.

**Why it happens:**
"React to images in chat" reads like a drop-in extension of the existing emoji-reaction pattern (`_handle_message_reactions`, YouTube/Spotify link → 👀), which is unthrottled by design because emoji reactions cost nothing. Vision is not free — it's an API call on the same budget `/ask` depends on, plus it's commenting on content the user did not opt into having analyzed.

**How to avoid:**
- Cadence-gate vision the same way ambient roasts are already gated: a probability roll (mirror `UNPROMPTED_ROAST_CHANCE` pattern) **and** a per-channel or per-user cooldown, so Dex doesn't comment on every image, only sometimes — this is both a quota control and a "not creepy/naggy" control (see Pitfall 4, same root cause).
- Route vision calls through **priority 2** (background, reject-if-wait>10s) on the shared limiter, never priority 1 — an unprompted image roast must never make a user's `/ask` wait. This mirrors the existing priority-tier discipline exactly (`_RateLimiter.acquire`, `services/gemini.py:74-102`).
- Designated-channel-only, same as every other unprompted behavior (Critical Rule 9) — do not scan attachments bot-wide.
- Consider a hard per-day or per-hour vision-call budget distinct from the roll-based gate, so a burst of image-posting (e.g., someone dumping a meme folder) can't chew through the day's RPD in minutes. `MAX_IMAGES_PER_USER_PER_DAY` already exists for `/imagine` outbound generation — a parallel cap for inbound vision analysis is the same shape of guardrail.
- Skip animated images (GIFs) and very small images (emoji-sized) before spending a call — cheap pre-filters that avoid burning budget on content unlikely to be roast-worthy.

**Warning signs:**
- `/stats` RPM-headroom panel (`GeminiService.rpm_headroom`, already exists) shows the budget saturating during periods of heavy image posting, not heavy `/ask` use.
- `/ask` responses start feeling slow/delayed after vision ships, with no other explanation.
- Vision fires visibly on back-to-back images in the same channel within seconds.

**Phase to address:** Vision / multimodal roasting — the cadence gate and priority-2 routing are core scope for this phase (VIS-01), not an afterthought.

---

### Pitfall 3: Proactive callbacks cross from "delightful" to "the bot is watching me"

**What goes wrong:**
A background surface that volunteers a memory unprompted — "hey, you were really into [artist] last week, want more of that?" — is qualitatively different from the *existing* ambient-roast pattern (voice join/leave, late-night, repeat-song) because those are all triggered by an **event the user just performed in the moment**. A callback that reaches back into memory and surfaces it at an arbitrary later time reads as surveillance the first time it lands on the wrong moment: firing during a serious conversation, firing right after a user explicitly stopped talking about something (breakup, job loss — anything the memory-sensitivity gate in Phase 11 was built to filter, but proactive surfacing adds a *timing* dimension that recall-for-a-question doesn't have), or simply firing too often so it stops feeling like insight and starts feeling like a scripted "engagement" nudge.

**Why it happens:**
The existing ambient-roast infrastructure (`cogs/events.py`, per-user cooldown dict, `UNPROMPTED_ROAST_CHANCE`) is trivially reusable — call `MemoryService.recall()`, pick a fact, post it, done. But that infrastructure was tuned for *reactive* triggers (something just happened) at a *known-good* moment (a voice join is inherently a moment where a light comment lands fine). A proactive callback has no such anchor moment by default; if the roadmap treats "reuse the roast cooldown dict" as sufficient, it will under-guard the one dimension that's actually new: **is right now a good moment to bring up something from the past, unprompted, with no triggering action from the user in this instant.**

**How to avoid:**
- Anchor callbacks to *some* proximate trigger, not a pure timer — e.g., only fire during/adjacent to an already-happening interaction (after a `/play` completes, when the user is already active in the channel), never as a cold "ping out of nowhere" while the user has been inactive.
- Cap frequency **per-user, across the whole surface**, more conservatively than ambient roasts — this is a new channel of attention, additive to existing roasts/reactions, so its budget should be a fraction of the existing roast cadence, not equal to it. Consider a hard daily cap per user (e.g., at most 1) in addition to a probability roll, mirroring the two-layer gate (`chance` + `cooldown`) already used for voice-join roasts.
- Reuse the memory-sensitivity gate (`is_sensitive()` in `models/memory.py`, Phase 11) as a **necessary but not sufficient** filter — sensitivity-screens content at write time; proactive surfacing needs an additional recency/freshness check so a callback doesn't resurrect something the user has clearly moved on from (see Pitfall 5, same underlying "stale memory" risk, amplified here because surfacing is unprompted rather than answering a direct question).
- Give users an explicit, discoverable opt-out (the planned `/memory forget` covers forgetting a *fact*; consider whether "stop proactive callbacks for me" needs to be a distinct, lighter-weight toggle rather than requiring users to delete their whole memory history to make it stop).
- Ship this behind a conservative default (low chance, high cooldown) and treat the numeric tuning as something to dial in from live observation, exactly as `UNPROMPTED_ROAST_CHANCE = 0.30` was presumably tuned by feel for a single community rather than derived analytically.

**Warning signs:**
- A callback fires twice in the same day for the same user.
- A callback references something from more than ~1-2 weeks ago with no signal the topic is still live (see Pitfall 5).
- Anecdotal server feedback uses words like "weird," "watching," "creepy," or "stalker" — treat this as a stop-ship signal for the feature's default cadence, not just a personality-tone note.

**Phase to address:** Proactive callbacks (fourth v1.3 feature area per PROJECT.md ordering, after RAG reach lands `/memory forget` as the escape hatch) — the cadence design should be reviewed explicitly against this pitfall before merge, not discovered live.

---

### Pitfall 4: Memory cross-user leakage — the existing guard is real but the surface area is growing

**What goes wrong:**
Phase 11 already scopes `search_memories` with a `WHERE user_id = $1` clause (`services/memory.py:114`, explicitly flagged in its own docstring as "cross-user guard T-11-03a"). That guard is sound for the *existing* callers (ambient roast, `/roast @user` presumably passing the target's `user_id`). The risk in v1.3 is **not** that the guard breaks — it's that new call sites (`/ask` with RAG wired in, `/memory`, taste-graph discovery, generative jams pulling shared listening history) multiply the number of places `recall()`/`search_memories` get invoked, and any one new call site that passes the wrong `user_id` (e.g., the *asker's* ID when the intent was "recall what we know about the mentioned user," or a guild-wide taste query that accidentally omits the `user_id` filter because taste-graph is conceptually "server-wide") reintroduces exactly the leak the guard was built to prevent — one user's private roast ammo surfacing in another user's `/ask` answer or the shared `/jam`.

**Why it happens:**
`recall(user_id, guild_id, query_text)` takes `user_id` as a plain parameter with no compile-time enforcement that the caller passed the *correct* one for the interaction's actual subject. The taste-graph and generative-jam features are new because they are explicitly **multi-user / server-wide** in a way `/ask` and ambient roasts are not (a shared `/jam` playlist already exists as a distinct concept from personal `user_favorites` — see Key Decisions in PROJECT.md). Code written for "aggregate across users for a jam recommendation" is one accidental refactor away from a query that forgets to scope by user for a *personal* recall.

**How to avoid:**
- Any new RAG call site added in v1.3 must be traced back to "whose memory is this and does the interaction's actual subject match the `user_id` passed" as an explicit code-review checklist item, not assumed correct by pattern-matching on existing calls.
- For genuinely multi-user surfaces (taste-graph, generative jams), design the query as an **explicit aggregate** (e.g., a dedicated `search_memories_multi_user` or a guild-scoped taste-signal table distinct from personal `user_memories`) rather than looping `recall()` per-user and hoping nothing crosses — an explicit aggregate function makes the multi-user intent visible in the schema/API instead of implicit in caller discipline.
- `/memory` (inspect/forget) must itself be scoped to `interaction.user.id` only — a user must never be able to inspect or forget another user's memories via the command, and the command's confirmation/echo must not leak fact *content* to anyone but the owning user (ephemeral response).
- Add a regression test (this bot already has a `logic/` pure-function test-coverage convention from Phase 10) asserting `search_memories` and any new multi-user aggregate never returns rows for `user_id`s outside the requested scope, given a fixture with 2+ users' memories seeded.

**Warning signs:**
- A `/roast @user` or taste-graph response contains a detail that doesn't match the target user's known history (best caught by the requester noticing something "off," which is a bad primary detection mechanism — prefer the test above).
- Any new SQL query touching `user_memories` that doesn't have a `user_id = $N` (or an explicit, reviewed multi-user aggregate) in its WHERE clause.

**Phase to address:** RAG reach (`/roast` + `/ask` wiring + `/memory`) — this is the phase that multiplies call sites; the taste-graph/jam multi-user surfaces (Smarter music brain phase) inherit the same discipline and should reuse whatever scoping pattern RAG reach establishes rather than inventing a second one.

---

## Moderate Pitfalls

### Pitfall 5: Stale or contradicted memories get surfaced as if still true

**What goes wrong:**
A memory written weeks ago ("user X is really into [artist]") gets surfaced by `recall()` or a proactive callback after the user's taste has visibly moved on — the auto-queue skip data, more recent `song_history`, or newer memories all show a shift, but the recalled fact is picked because it scores well on similarity/salience without the reranker weighing "has this been contradicted by more recent, higher-confidence signal." Phase 11's `rerank()` already includes a recency weight and a novelty penalty on `last_surfaced_at` (`config.MEMORY_RERANK_RECENCY_WEIGHT`, `MEMORY_RERANK_NOVELTY_WEIGHT`) — but recency-of-the-memory-itself is not the same signal as "is this still true," and the accuracy firewall (Phase 11 Key Decision: "hard numbers come from live SQL, never from embedded facts") only guards *numeric* accuracy, not *directional* accuracy (taste has changed vs. taste hasn't).

**Why it happens:**
The existing rerank formula optimizes retrieval relevance (similarity × recency × salience × novelty), not truthiness-over-time. Nothing in the current pipeline cross-checks a recalled fact against fresher structured data (`song_history`, `user_artist_counts`) before injection — this matters more in v1.3 because taste-aware auto-queue and generative jams are *exactly* the features most likely to actively contradict an old memory (a user's listening pattern is the ground truth the memory was distilled from in the first place).

**How to avoid:**
- Where a recalled memory concerns music taste specifically, cross-check against recent `user_artist_counts`/`song_history` before using it to drive a *decision* (auto-queue selection) — use memory as flavor/roast text, never as the sole input to what gets queued. This mirrors the existing "memory is roast ammo, not a number source" firewall, extended to "memory is roast ammo, not a queue-decision source" for the music brain.
- Consider a lighter decay curve or explicit "superseded" marking for taste-kind memories specifically, since taste memories churn faster than personality/history facts (a repeat-song roast fact stays true forever; a "likes artist X" fact has a much shorter half-life).
- For proactive callbacks specifically (Pitfall 3), bias toward *higher* recency weight than `/ask`/`/roast` recall uses, since a stale callback is more visibly wrong (unprompted) than a stale fact folded into an answer to a direct question.

**Warning signs:**
- A callback or roast references a taste fact contradicted by the last 2 weeks of `song_history` for that user.
- `MEMORY_DECAY_DAYS`/salience-floor tuning from Phase 11 (tuned for general facts) is reused unmodified for the new "taste episode" memory kind without revisiting whether the same horizon fits.

**Phase to address:** Semantic music memory (foundation phase) should decide the taste-memory kind's decay/rerank parameters deliberately rather than inheriting Phase 11's general-fact defaults; Smarter music brain phase should enforce "memory informs, structured data decides" for auto-queue.

---

### Pitfall 6: `/memory forget` deletes the row but not everything derived from it

**What goes wrong:**
A user runs `/memory forget` expecting a fact to be gone. If the implementation only does `DELETE FROM user_memories WHERE id = $1`, that's actually sufficient for the embedding itself (pgvector stores the embedding *in* the row, not in a separate index structure the app must also clean — HIGH confidence, this is standard pgvector column-storage behavior already implied by the Phase 11 schema). The real gaps are downstream: any *cached* recall result already injected into an in-flight conversation isn't retracted, and — more importantly — if the forgotten fact had already been referenced in a **later** distilled memory (e.g., a milestone/callback roast that got itself written back into memory as a new episode, or a generative-jam "continue this jam" episode derived partly from the now-forgotten taste fact), that derivative memory persists and can effectively resurrect the "forgotten" information indirectly.

**Why it happens:**
`remember()`/`distill_and_remember()` create new memories from bot-generated text (roast responses, jam summaries) as well as from user behavior — this is a legitimate part of the design (memory that compounds on itself), but it means "delete the source fact" doesn't transitively delete facts that were derived *from* observing the source fact's effects (e.g., Dex roasting the user about it, which itself got distilled into a new memory).

**How to avoid:**
- Ship `/memory forget` with an accurate scope statement to the user: it deletes the specific stored fact and its embedding; it does not (unless explicitly built to) find and delete facts that were distilled from Dex's own commentary about the original fact. Set this expectation explicitly in the command's response text rather than implying total erasure.
- If full "right to be forgotten" semantics matter for this bot (reasonable for a personality bot roasting real people), consider a `/memory forget-all` scoped to a user that clears their entire `user_memories` row set, not just single-fact forgetting, as the actually-reliable erasure path.
- Verify the DELETE actually removes the pgvector embedding column (not just a "soft delete"/tombstone flag) — check the Phase 11 schema definition in `database.py` for whether `evict_lowest_salience`/deletion helpers do hard deletes (they should, based on the sweep/eviction pattern already described in `services/memory.py`, but confirm for the new `/memory forget` code path specifically since it's a new caller).

**Warning signs:**
- A "forgotten" fact's substance reappears in a later roast (via a derivative memory that wasn't cleared).
- `/memory forget` responds with a success message but a follow-up `/memory` inspect still surfaces semantically-equivalent content from a different row.

**Phase to address:** RAG reach (`/memory` command scope).

---

### Pitfall 7: Auto-queue feedback loop narrows the playlist into a filter bubble

**What goes wrong:**
"Taste-aware auto-queue that learns from `was_skipped`" (already a tracked column per CLAUDE.md schema) can converge into a self-reinforcing loop on a shared server: it recommends what was previously accepted, gets accepted again (confirmation bias — accepting isn't the same as loving it, sometimes it's just not bothering to skip), and the taste model narrows toward an increasingly generic "safe" genre while variety-seeking recommendations that *would* have been skipped never get tried in the first place because the model learned to avoid anything skip-adjacent. This is worse in a **shared server** context than a personal-recommendation system: auto-queue optimizes toward whichever users are most active/vocal (skip button = signal), silently under-serving quieter members' taste, and multiple users' conflicting taste signals get averaged into bland middle-of-the-road picks that satisfy no one.

**Why it happens:**
`was_skipped` is a strong, easy-to-use negative signal; there's no equivalent strong positive signal (a song playing to completion isn't necessarily "loved," it might just be tolerated background noise), so a naive model trained more on avoiding skips than pursuing genuine engagement will drift toward the statistically safest, least-skippable common denominator — generic, inoffensive picks — rather than toward what any specific listener actually wants. Phase 12 already validates hallucinated *track identity* (token-set containment against the YouTube result) — that guards against the model inventing songs that don't exist, not against the model converging on a boring but real subset of songs.

**How to avoid:**
- Explicitly inject some exploration/diversity budget into auto-queue selection (don't purely exploit the skip-avoidance signal) — e.g., reserve a fraction of auto-queued picks per round for genre/artist not recently played, even if slightly higher skip-risk.
- Track auto-queue picks per *contributing user* where the session has multiple listeners, not just server-wide aggregate taste, so the "ignored" memory (already an existing Phase 2 concept — track skip rate on auto-queued songs) doesn't collapse multiple people's distinct taste into one blended profile.
- Treat "cold-start" (a session/user with little history) as an explicit branch, not an edge case that falls through to whatever the empty-history code path happens to do — fall back to genre/mood-based recommendation from the *currently playing* session context (existing `AUTO_QUEUE_SONGS_PER_ROUND`/session-lookback pattern from Phase 2) rather than a global-server-average taste that may not represent anyone in the current voice channel.
- Cap how heavily any single memory-derived taste signal can dominate a round's picks (mirrors the existing `MEMORY_INJECT_CAP` discipline of capping how much any one signal source can dominate a single generation).

**Warning signs:**
- Auto-queue picks trend toward a narrowing genre/artist set over weeks, visible in `/skips` analytics (already shipped in Phase 12) or `user_artist_counts` diversity dropping server-wide.
- A quiet/less-active user's taste never shows up in auto-queue picks despite being logged in `song_history`.
- New users (cold-start) get generic/bland picks indistinguishable from the server-average rather than anything responsive to what they just played.

**Phase to address:** Smarter music brain.

---

### Pitfall 8: Message-content intent + attachment edge cases silently break vision

**What goes wrong:**
The `message_content` intent is already enabled (required today for message-buffer context), so the bot *can* see attachments — but "an image was posted" has more edge cases than "there's a URL in `message.attachments`": images embedded via URL in the message *text* rather than as a Discord attachment (a pasted link to an external image host) won't appear in `message.attachments` at all; Discord CDN attachment URLs are **ephemeral/signed and expire** — if the vision call is deferred, retried, or run through a background queue rather than handled synchronously in `on_message`, the fetch can 404 by the time it runs; non-image attachments (video, other file types) need a content-type check before being handed to the vision model; multiple images in one message need a decision (comment on the first only? all of them, multiplying cost?); and edited messages that *add* an image after the fact won't be caught by an `on_message`-only listener (would need `on_message_edit` too, which most implementations correctly skip as unnecessary scope).

**Why it happens:**
The existing `on_message` handler (`cogs/events.py:347-364`) does zero attachment inspection today — vision is entirely new surface area, so there's no existing pattern to copy correctly or incorrectly from within this codebase; every edge case has to be designed fresh.

**How to avoid:**
- Filter to `message.attachments` with `content_type` starting `image/` (Discord provides this) before any Gemini call — explicitly do not attempt to fetch arbitrary URLs found in message text (scope creep + SSRF-adjacent risk fetching arbitrary user-supplied URLs server-side).
- Handle vision synchronously within the `on_message` flow (fetch attachment bytes immediately, don't defer to a later background pass) specifically because Discord attachment URLs are signed/expiring — don't build a queue-and-process-later architecture for this without also either re-fetching the message or caching the bytes at receipt time.
- Cap to the first image if multiple are attached (matches "one emoji max," "one comment max" personality economy — commenting on every image in a multi-image post is spammy and multiplies quota cost for one message).
- Explicitly skip GIFs/video/non-static images (either by content-type or a max-file-size heuristic) rather than sending them to a vision model built for still images.

**Warning signs:**
- Vision "randomly" fails on some images with a fetch/404 error in logs — check whether it's happening on deferred/retried calls specifically (expired CDN URL).
- Cost/RPM spikes disproportionate to message count — check for multi-image messages triggering multiple calls.

**Phase to address:** Vision / multimodal roasting.

---

## Minor Pitfalls

### Pitfall 9: Fire-and-forget errors in new background paths vanish silently

**What goes wrong:**
Phase 9 already solved this generally (`utils/tasks.py` `make_task` — done-callback surfaces fire-and-forget exceptions to logs/error channel, per CLAUDE.md Implementation Gotchas). The risk in v1.3 isn't that the fix doesn't exist — it's that **new** fire-and-forget call sites (proactive callback scheduling, background taste-graph recomputation, vision analysis dispatched from `on_message`) get written as raw `asyncio.create_task(...)` without routing through `make_task`, because it's easy to pattern-match on the *older*, pre-Phase-9 auto-queue/`distill_and_remember` style (which is itself already correctly self-contained with internal try/except, per `services/memory.py`) rather than the explicit `make_task` wrapper convention.

**How to avoid:**
Grep for every new `asyncio.create_task(` added in v1.3 diffs and confirm each one either (a) routes through `make_task`, or (b) has the same self-contained catch-everything-and-log discipline `MemoryService.remember`/`distill_and_remember` already demonstrate. Make this an explicit code-review checklist line for v1.3, since it's a cross-cutting concern touching every new feature area.

**Phase to address:** All v1.3 phases — call out as a standing review checklist item, not owned by one phase.

---

### Pitfall 10: Blocking the event loop with synchronous image/embedding work

**What goes wrong:**
Vision and taste-graph features are natural places to reach for a synchronous image-processing library (e.g., PIL to resize/validate an image before sending to Gemini) or a synchronous numpy/sklearn call for taste-graph clustering. Any CPU-bound synchronous call inside an `async def` handler blocks the entire bot's event loop — stalling every guild's playback callback handling, not just the one interaction — same class of bug the codebase already guards against for FFmpeg (explicit subprocess handling, never blocking).

**How to avoid:**
Any non-trivial synchronous CPU work (image resize/validation, taste-graph clustering/aggregation over more than a handful of rows) should go through `asyncio.to_thread(...)` or be pushed into the existing background-task pattern rather than awaited inline. Keep it in mind specifically for: image pre-validation before the vision API call, and any taste-graph "compute a graph/cluster" step if it's done in-process rather than via a SQL aggregate query (prefer SQL aggregation over in-Python clustering where possible — it's both faster and avoids the blocking risk entirely).

**Phase to address:** Smarter music brain (taste-graph), Vision / multimodal roasting.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|-----------------|------------------|
| Reuse `UNPROMPTED_ROAST_CHANCE`-style single probability roll for proactive callbacks with no additional daily cap | Fast to ship, one config constant | Creepy-factor risk (Pitfall 3) goes untested until live feedback | Never for callbacks — always pair a roll with a hard per-user daily cap |
| Loop `recall()` per-user for taste-graph instead of a dedicated multi-user aggregate query | Reuses existing function, no new SQL | Silent cross-user leak risk if any loop iteration passes the wrong `user_id` (Pitfall 4) | Only for a throwaway prototype/spike, never merged |
| Treat all Gemini vision refusals as "fall back to generic roast" | Simplest error handling, one code path | Defeats content-safety guardrails (Pitfall 1) — literally the risk being guarded against | Never |
| Skip cold-start branch for auto-queue, let empty-history fall through to whatever default exists | Less code | New users get server-average bland picks, feels broken (Pitfall 7) | Acceptable only if server has one dominant listener already (single-user or near-single-user community) |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|-----------------|-------------------|
| Gemini vision (`gemini-2.5-flash`, multimodal) | Assuming vision calls are "free" against the 15 RPM budget because they're framed as a "reaction," not a "command" | Route through the same shared limiter at **priority 2**, same as background auto-queue — an unprompted image roast must never contend with `/ask`/`/imagine` |
| Gemini safety settings | Setting `BLOCK_NONE` on all categories to "let more images through" | Leave adjustable categories at a sane default threshold; `BLOCK_NONE` has no upside since CSAM/child-safety blocking is non-configurable and always-on regardless |
| Discord CDN attachment URLs | Fetching attachment bytes in a deferred/queued background task | Fetch synchronously at message-receipt time — CDN URLs are signed and expire |
| pgvector / `user_memories` (new call sites) | Assuming the existing `WHERE user_id` guard in `search_memories` automatically protects every new caller | Every new call site must explicitly pass and verify the correct `user_id` scope; add a cross-user regression test |
| `/memory forget` | Treating a single-row DELETE as complete erasure | Document the actual scope (source fact only, not derivative memories) or build `forget-all` for real erasure semantics |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|-----------------|
| Unthrottled vision on every image attachment | RPM budget saturates, `/ask` starts feeling slow/delayed | Cadence gate (chance + cooldown) + priority-2 routing + designated-channel-only | First burst of image-heavy chatter after ship (could be day one) |
| Proactive callback timer with no daily cap | Same user gets multiple unprompted callbacks per day | Hard per-user daily cap alongside the probability roll | Immediately, on the first unlucky roll streak for an active user |
| In-Python taste-graph clustering on every invocation instead of cached/SQL-aggregated | Command latency grows with `song_history` size; risks event-loop blocking (Pitfall 10) | Precompute/cache taste-graph on a schedule, or push aggregation into SQL | Once `song_history` reaches a size where in-Python grouping takes more than a few hundred ms |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Treating Gemini's safety filters as the only content-safety gate for vision | Legal/ToS exposure if the model complies with a request Gemini allows but is still inappropriate to roast (nudity-adjacent-but-not-blocked, images of minors who aren't clearly the poster, private/medical images) | Add an application-level system-prompt hard-rule layer on top of Gemini's own filters (Pitfall 1) |
| Fetching arbitrary image URLs found in message *text* (not Discord attachments) | SSRF-adjacent risk (bot server fetching attacker-controlled URLs), plus scope creep | Scope strictly to `message.attachments` with `content_type` starting `image/` |
| `/memory` inspect echoing another user's fact content to the invoker (via a malformed target-user parameter) | Cross-user privacy leak of roast-ammo-grade personal facts | Scope `/memory` hard to `interaction.user.id`; never accept a target-user argument for inspect/forget |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-------------------|
| Vision comments on every image, including ones users didn't want analyzed (private screenshots, ID photos shared for an unrelated reason) | Feels invasive; erodes trust in the designated channel | Cadence-gate + skip anything ambiguous rather than commenting; when in doubt, stay silent |
| Proactive callback lands mid-serious-conversation | Feels tone-deaf at best, upsetting at worst | Anchor callbacks to an already-active, low-stakes moment (music playback, casual chatter), never a cold interrupt |
| Auto-queue converges to bland server-average picks | Feels like the bot "stopped listening" to individual taste | Preserve exploration budget + per-user signal tracking within shared sessions (Pitfall 7) |
| `/memory forget` implies total erasure but leaves derivative memories | User trusts a false sense of privacy control | Accurate command copy about scope, or a real `forget-all` |

## "Looks Done But Isn't" Checklist

- [ ] **Vision content-safety:** Often missing an application-level hard-rule layer beyond Gemini's own filters — verify the system prompt explicitly forbids appearance/body/medical commentary, not just relying on the model's judgment.
- [ ] **Vision refusal handling:** Often missing the distinction between "safety refusal → silently skip" vs. "rate-limited/API error → template fallback" — verify these are two different code branches, not one.
- [ ] **Proactive callback cadence:** Often missing a hard per-user daily cap in addition to the probability roll — verify both exist, not just the roll.
- [ ] **Multi-user RAG call sites (taste-graph, jams):** Often missing an explicit multi-user-scoped query distinct from personal `recall()` — verify no per-user loop that could leak scope.
- [ ] **`/memory forget`:** Often missing coverage of derivative memories (facts distilled from Dex's own commentary about the forgotten fact) — verify the command's stated scope matches its actual behavior.
- [ ] **Auto-queue cold-start:** Often missing an explicit branch — verify new users/sessions get session-context-based recommendations, not silently-empty or bland server-average picks.
- [ ] **Attachment content-type filtering:** Often missing a check that skips GIFs/video/non-image attachments before spending a vision API call — verify the filter exists before the Gemini call, not after.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|-----------------|------------------|
| Vision roasted an inappropriate image before guardrails were tightened | MEDIUM | Delete the bot's message if still possible, tighten the system-prompt hard-rule layer and safety thresholds, add the specific case to a regression checklist, review error-channel logs for similar near-misses |
| Proactive callback creeped out the server | LOW | Reduce chance/raise cooldown in config immediately (no redeploy needed if these are env-tunable), consider pausing the feature entirely behind a flag while retuning |
| Cross-user memory leak discovered in `/ask` or taste-graph | HIGH | Immediately audit every `search_memories`/`recall()` call site for missing `user_id` scoping, add the regression test from Pitfall 4, consider a full memory-table review for any facts that may have already leaked and whether affected users need direct notice |
| Auto-queue visibly converged into a bland filter bubble | LOW-MEDIUM | Temporarily widen the exploration budget in config, backfill `/skips` analytics review to identify the narrowing pattern, consider a manual "reset taste memory" for the affected server |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-------------------|----------------|
| Content-safety / legal risk of vision roasting (P1) | Vision / multimodal roasting | Safety-refusal branch is distinct from API-error branch in code review; refusal logs reviewed during rollout; system prompt has explicit hard-rule section |
| Vision quota/privacy blowout from unthrottled reactions (P2) | Vision / multimodal roasting | `/stats` RPM headroom stays stable through an image-heavy test period; cadence gate + priority-2 routing present in code review |
| Proactive callback creepiness (P3) | Proactive callbacks | Daily-cap + probability-roll both present; callbacks anchored to an active-moment trigger, not a cold timer; live feedback monitored post-ship |
| Cross-user memory leakage on new call sites (P4) | RAG reach (foundation for the pattern); Smarter music brain (inherits it) | Regression test asserting scoped queries never cross `user_id`; code review checklist item for every new `recall()`/`search_memories` caller |
| Stale/contradicted memory surfaced as current (P5) | Semantic music memory (foundation); Smarter music brain (enforcement) | Taste-kind memory decay/rerank params deliberately set, not inherited unmodified from Phase 11 general-fact defaults; auto-queue uses structured `song_history`/`user_artist_counts` as the decision source, memory as flavor only |
| `/memory forget` incomplete erasure (P6) | RAG reach | Command copy accurately states scope; hard-delete confirmed (not soft-delete) for the direct row |
| Auto-queue feedback loop / filter bubble (P7) | Smarter music brain | Exploration budget present in selection logic; per-user signal tracked within shared sessions; cold-start has an explicit branch |
| Attachment/message_content edge cases (P8) | Vision / multimodal roasting | Content-type filter present before any Gemini call; synchronous fetch-at-receipt-time confirmed; multi-image messages capped to one |
| Fire-and-forget errors vanish in new background paths (P9) | All v1.3 phases (standing review item) | Every new `asyncio.create_task` in the diff routes through `make_task` or has equivalent self-contained error handling |
| Event-loop blocking from synchronous image/clustering work (P10) | Smarter music brain; Vision / multimodal roasting | No CPU-bound synchronous call inside an `async def` without `asyncio.to_thread`; taste-graph aggregation done in SQL where feasible |

## Sources

- `services/gemini.py` (this repo) — existing `_RateLimiter` priority-tier mechanics, `GeminiRefusalError` defined-but-unused, `generate_image` refusal-as-`None` pattern
- `services/memory.py` (this repo) — Phase 11 RAG `recall`/`remember`/`distill`/`sweep` pipeline, existing cross-user guard (`search_memories` `WHERE user_id`), sensitivity/number safety gates, fire-and-forget error-swallowing discipline
- `cogs/events.py` (this repo) — existing ambient-roast cadence-gate pattern (probability + per-user cooldown dict), `on_message` handler with zero attachment inspection today (vision is greenfield)
- `.planning/PROJECT.md`, `CLAUDE.md` (this repo) — v1.3 scope, Critical Rules, Phase 9-12 Implementation Gotchas this research builds on rather than repeats
- [Gemini API safety settings](https://ai.google.dev/gemini-api/docs/safety-settings) — confirmed CSAM/child-safety filtering is non-configurable and always-on; four adjustable harm categories are separate from this hard block; MEDIUM-HIGH confidence (official docs, cross-checked via WebSearch summary)
- [Gemini API image understanding](https://ai.google.dev/gemini-api/docs/image-understanding) — confirmed base image token cost (258 tokens for images ≤384px per dimension) and tiling behavior for larger images (768×768 tiles, 258 tokens each); MEDIUM confidence (fetched via WebFetch, page did not include free-tier-specific numeric RPD/TPM caps)
- [Gemini API rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) — confirmed free-tier numeric RPM/TPM/RPD values are account/tier-dependent and surfaced live in AI Studio rather than published as static docs constants; LOW-MEDIUM confidence on any specific number, recommend verifying current limits in AI Studio before finalizing config for the vision phase
- General WebSearch on Gemini 2.5 Flash free-tier pricing/limits — MEDIUM-LOW confidence, third-party summaries vary and reference figures that shift; treat as directional only, verify against AI Studio at implementation time

---
*Pitfalls research for: Dexter v1.3 "Taste Brain" (semantic music memory, taste-aware auto-queue, RAG reach, proactive callbacks, vision/multimodal roasting)*
*Researched: 2026-07-02*
