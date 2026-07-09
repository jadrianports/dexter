# Architecture Research — v1.3 "Taste Brain"

**Domain:** Integration architecture for new features into an existing Discord bot
**Researched:** 2026-07-02
**Confidence:** HIGH (grounded in direct reads of bot.py, services/memory.py, services/gemini.py,
cogs/ai.py, cogs/events.py, database.py, models/memory.py, logic/*, config.py, plus a Context7
verification of the `google-genai` multimodal `Part.from_bytes` API)

> **Mandate:** integrate, do NOT redesign. This supersedes the Phase 11 (v1.2) ARCHITECTURE.md
> that previously lived at this path — that research is now historical; this file addresses
> the v1.3 "Taste Brain" milestone (semantic music memory, smarter auto-queue/discovery/jams,
> RAG into `/roast`+`/ask`, proactive callbacks, vision).

## Summary

v1.3 does not need a new storage layer, a new rate-limit budget, or a new task-scheduling
mechanism — it needs five additions layered onto exactly the seams v1.2 already built:

1. **Taste memory** extends `user_memories`/`MEMORY_SALIENCE_BASE_WEIGHTS` with new `kind`
   values, written by a new distillation pass over `song_history` (not message buffer).
   It is consumed two ways: qualitative flavor via the *existing* `MemoryService.recall()`
   (kind-agnostic, no code change needed there), and quantitative signal via *new* structured
   SQL aggregates in `database.py` (never embedded — the accuracy firewall from Phase 11
   forbids putting SQL-known numbers in vector text).
2. **Taste-graph / recommendation logic** is a new pure `logic/taste.py` module (scoring,
   ranking, "what to suggest next") fed by a new `services/taste.py` that orchestrates SQL +
   Gemini + (optionally) `MemoryService.recall()` — because three consumers (auto-queue, a
   new discovery command, generative jams) would otherwise duplicate the same fetch/rank
   glue across cogs.
3. **RAG into `/roast` + `/ask`**: zero new components — `recall()` is already wired into
   both (dormant only in the sense that the injected memories are currently just whatever
   `kind`s exist; once taste memories are written, they show up for free).
4. **Proactive callbacks** are a new `@tasks.loop` in `bot.py` (mirroring `memory_sweep` /
   `memory_distill_batch` placement, NOT cog-owned — no background loop in this codebase
   lives inside a cog), gated by a new pure decision function mirroring
   `logic/roasts.py:decide_ambient_roast`.
5. **Vision** is a new `cogs/vision.py` (mirrors the `imagine.py` vs `ai.py` split — vision
   is its own feature domain, not an addition to `events.py`), with a new
   `GeminiService.describe_image()` method verified against the current `google-genai` API
   (`types.Part.from_bytes(data=..., mime_type=...)` inside `types.Content`), sharing the
   existing 15 RPM chat limiter at priority=2 (background/ambient, never contends with
   `/ask`).

No new tables, no new Postgres extensions, no new rate limiters, no new external services.
Every new piece slots into an existing pattern that already has a name in this codebase.

## Integration Points

### (a) Taste/listening memory kind

**Extend `user_memories` + `MEMORY_SALIENCE_BASE_WEIGHTS`. Do not create a separate table.**

- `models/memory.py` (`MemoryFact`, `apply_floor`, `rerank`, `dedup_decision`,
  `choose_eviction`, `compute_salience`, `decay_predicate`) and `services/memory.py`
  (`recall`/`remember`/`distill`/`distill_and_remember`/`sweep`) are already fully generic
  over `kind` — `database.search_memories` has no `kind` filter, only `WHERE user_id = $1`.
  Adding new kinds requires **zero changes** to the recall/rerank/dedup/eviction pipeline.
- Add new keys to `config.MEMORY_SALIENCE_BASE_WEIGHTS` (`config.py:181`), e.g.:
  - `"taste_episode": 0.3` — a periodic, qualitative distillation of a user's listening
    vibe ("gravitates toward moody synth-pop late at night"). Sits just above
    `daily_batch` (0.2) on the existing ordinal ladder — background-confidence signal,
    not milestone-tier.
  - Optionally `"taste_shift": 0.4` if the roadmap wants a distinct "your taste is
    drifting" signal, matching `auto_queue_ignored`'s tier (negative-preference class).
  - **Do not** invent a `kind` for skip-rate learning — that stays structured (see below).
- **What writes it, and when:** a new daily/periodic distillation pass, structurally a
  sibling of `bot.py:memory_distill_batch` (`bot.py:808-889`) but reading `song_history` +
  `user_artist_counts` instead of `bot.message_buffer`. Candidate hook points, in order of
  preference:
  1. **New `@tasks.loop` `taste_distill_batch`** (daily, off-peak like the existing 02:30/
     03:00/04:00 UTC loops — pick an unused slot, e.g. 03:30 UTC, to avoid Neon
     thundering-herd per the existing comment at `bot.py:906-909`). For each user active in
     `song_history` in the last 24h, build a compact raw-text summary (top artists, any
     new-artist binge, any single-artist repeat) and call
     `memory_service.distill_and_remember(kind="taste_episode", ...)`. This reuses
     `distill()`'s existing number/PII backstop (`is_sensitive`, `contains_number`) for free
     — important, since raw song titles/counts must never leak into the embedded text
     (accuracy firewall, Critical Rule 5).
  2. **Event hook at queue-exhaustion / session-end** (where `try_auto_queue` already fires,
     `cogs/music.py:787`) is a secondary/optional trigger for a "session recap" fact,
     mirroring the `auto_queue_ignored` fire-and-forget pattern already in
     `cogs/ai.py:402-435` — same `make_task(..., bot=self.bot)` call shape.
- **Two distinct data paths — do not conflate them:**

  | Signal | Storage | Why |
  |---|---|---|
  | Qualitative vibe/genre commentary (roast ammo, jam flavor) | `user_memories`, new `kind`s, via `MemoryService` | Matches existing episodic-RAG design; feeds `/roast`, `/ask`, discovery flavor text, jam prompts for free through `recall()` |
  | Skip-rate / artist-affinity weighting for auto-queue ranking | `song_history.was_skipped` + `user_artist_counts` (existing tables), read via **new** structured SQL helpers | Numbers/counts must come from live SQL, never from embedded vector text (Phase 11 accuracy firewall, `models/memory.py:contains_number`, CLAUDE.md Critical Rule 5) |

### (b) Taste-graph / recommendation logic — pure `logic/` vs service

- **New pure module: `logic/taste.py`** (mirrors `logic/autoqueue.py`'s
  `validate_youtube_match` and `logic/roasts.py`'s `decide_ambient_roast` conventions — no
  Discord, no asyncio, no DB, no `random`/`datetime.now()`; nondeterministic values passed
  in by the caller). Candidate pure functions:
  - `compute_artist_affinity(play_counts: dict[str,int], skip_counts: dict[str,int]) -> list[ArtistAffinity]`
    — combine play count and skip penalty into a ranked affinity score. This is the
    taste-graph's scoring core and is the single highest-value thing to unit-test, since it
    is exactly the kind of branchy arithmetic that caused the three named scar regressions
    in Phase 10.
  - `filter_recent_repeats(candidates, recently_played, window) -> list[...]` — discovery/
    jam-generation novelty filter (don't resuggest what's already in the last N plays).
  - `rank_discovery_candidates(affinities, candidate_pool) -> list[...]` — feeds the new
    `/discover`-style command.
  - A scoring hook auto-queue's suggestion loop can call before/alongside the current
    unconditional accept in `cogs/ai.py:311-364` (`try_auto_queue`'s per-suggestion loop) —
    e.g. `should_deprioritize_artist(artist, skip_rate, threshold)`.
  - Reuse `logic/autoqueue.py:validate_youtube_match` unchanged — it stays the
    YouTube-result-vs-suggestion string validator; taste scoring is a distinct concern
    layered before/after it, not a replacement.
- **New service: `services/taste.py` (`TasteService`)**. Justification: three consumers
  (auto-queue in `cogs/ai.py`, a new taste-graph discovery command, generative jams in
  `cogs/library.py` or a new cog) would otherwise each independently glue together SQL +
  Gemini + `logic/taste.py` + optional `MemoryService.recall()`. Centralizing that glue in
  one service is exactly why `MemoryService` itself exists (its own docstring: "This file is
  the only place that wires together GeminiService.embed(), the database... and the
  pure-logic scoring functions"). `TasteService` should own:
  - `get_taste_profile(user_id | guild_id) -> TasteProfile` — structured SQL fetch
    (artist counts + skip stats) + `logic/taste.py:compute_artist_affinity`.
  - `recommend_candidates(profile, count) -> list[dict]` — Gemini prompt call (new prompt
    builder in `personality/prompts.py`, parsed with the same tolerant-JSON pattern as
    `cogs/ai.py:parse_suggestions`) + `logic/taste.py` filtering.
  - `taste_flavor_text(user_id, guild_id, anchor) -> list[str]` — thin pass-through to
    `self._memory.recall(...)` for qualitative flavor, kept in the service so callers don't
    each re-derive the recall-anchor string convention.
  - Constructor takes `(pool, gemini_service, memory_service)` and is wired in
    `bot.py:_initialize_once` right after `bot.memory_service` is constructed
    (`bot.py:415-418`), following the exact same `if hasattr(bot, "gemini_service")` /
    `if hasattr(bot, "memory_service")` guard chain — taste features degrade silently when
    Gemini is unconfigured, same as memory does today.
- **Cog layer** (`cogs/ai.py::try_auto_queue`, a new discovery command, jam-generation)
  stays orchestration-only: call `bot.taste_service`, never touch `database.py` or
  `logic/taste.py` directly — mirrors how `cogs/ai.py` today calls `MemoryService.recall()`
  rather than `database.search_memories` directly.

### (c) How the music brain retrieves taste

- **Structured (primary, for auto-queue ranking):** new `database.py` helpers, siblings of
  the existing `get_user_skip_rate` (`database.py:1224-1246`, Phase 12 precedent for exactly
  this kind of guild+user-scoped aggregate). Add something like
  `get_artist_play_and_skip_counts(pool, *, guild_id, user_id | None) -> list[Record]`
  joining `song_history` (`title`/`artist`/`was_skipped`) with `user_artist_counts`
  (`play_count`). This is what `services/taste.py` calls before invoking
  `logic/taste.py:compute_artist_affinity`. **Not** a call through `MemoryService` — numbers
  must come from live SQL per the accuracy firewall, and this needs to run on every
  auto-queue round (priority=2, latency-sensitive), where an extra embedding round-trip
  would be wasteful.
- **Semantic (secondary, for qualitative flavor — jam prompts, discovery blurbs):** reuse
  `MemoryService.recall()` completely unchanged. Because `search_memories` has no `kind`
  filter, `taste_episode` facts written by the new distillation pass will surface through
  the *existing* recall call sites in `cogs/events.py:_generate_ambient_roast` and
  `cogs/ai.py`'s `/ask` and `/roast` automatically, ranked by the same salience/recency/
  novelty composite as every other memory kind — this is what "RAG into `/roast` + `/ask`"
  in the milestone brief actually means: no new recall plumbing, just new facts flowing
  through the pipe that already exists.
- **Gotcha to flag for the roadmap:** `recall()` is scoped to a single `user_id`
  (`services/memory.py:60-97`, `database.py:search_memories` `WHERE user_id = $1`). A
  guild-wide "taste-graph discovery" command needs guild-scoped structured aggregation
  (`song_history WHERE guild_id = $1`, cross-user), not N per-member `recall()` calls (which
  would burn N embed-RPM slots per invocation). Use the structured path for anything
  guild-scoped; reserve `recall()` for anything user-scoped and qualitative. This mirrors
  how `auto_queue_ignored` already writes (`cogs/ai.py:402-435`) — one `distill_and_remember`
  call **per voice member**, individually scoped — but that pattern should not be reused for
  *reading* a guild aggregate; it's fine for *writing* per-user signal.

### (d) Proactive callbacks

- **New `@tasks.loop`, placed in `bot.py`, not inside a cog.** Every existing background
  loop in this codebase (`idle_check`, `cache_cleanup`, `ytdlp_update`, `status_rotation`,
  `memory_distill_batch`, `memory_sweep`) lives at module scope in `bot.py`, each with a
  paired `.before_loop` (`wait_until_ready`) and `.error` handler routed through
  `_post_loop_error` (`bot.py:637-664`). A new `proactive_callback` loop should follow that
  exact template — including registration in `_cleanup_partial_init`'s stop-list
  (`bot.py:280-281`) so a botched boot doesn't leave it firing against a torn-down pool.
- **Cadence / "good moment" heuristic** — new pure decision function,
  `logic/roasts.py:decide_proactive_callback(...)` (extend the existing file rather than a
  new `logic/proactive.py`, since it is conceptually a sibling of `decide_ambient_roast` and
  shares `is_late_night`/cooldown-style helpers), taking:
  - `chance_roll: float` — new `config.PROACTIVE_CALLBACK_CHANCE` (suggest 0.15–0.20, lower
    than `UNPROMPTED_ROAST_CHANCE`'s 0.30 since this fires on a timer across *all* guilds
    rather than on a per-event trigger — a higher chance would spam).
  - `seconds_since_last: float` + new `config.PROACTIVE_CALLBACK_COOLDOWN_SECONDS` (suggest
    1–2 hours, not `AMBIENT_ROAST_CEILING_SECONDS`'s 300s — this is a per-guild cooldown
    tracked in a new module-level dict in `bot.py`, e.g. `_last_proactive_callback:
    dict[int, float]`, same shape as `_last_loop_error_post`).
  - `has_active_voice: bool` + `human_count: int` — reuse the exact `bot.voice_clients` +
    `[m for m in vc.channel.members if not m.bot]` scan already in `idle_check`
    (`bot.py:670-681`).
  - **Avoiding spam / picking a good moment:** the single strongest signal already in the
    codebase is `idle_check`'s loneliness accumulator (`vc._idle_loneliness_seconds`,
    `bot.py:703-740`) — it already detects "voice is occupied but quiet" and gates a
    once-per-silence-window post. Rather than building a second quiet-detector, the
    proactive-callback loop should run at a coarser interval (e.g. every 10–15 min, new
    `config.PROACTIVE_CALLBACK_INTERVAL_SECONDS`) and only consider guilds where
    `vc._loneliness_posted` is already `True` (i.e., idle_check has already established the
    channel is quiet) — piggybacking on existing state instead of recomputing "is this a
    good moment" from scratch. This keeps the two loops decoupled (different concerns,
    different config knobs) while sharing the one signal that actually matters.
- **Fetch + post:** on a pass, call `memory_service.recall(user_id, guild_id, anchor)` for
  one human member of a quiet, occupied voice channel (pick randomly among eligible members
  — do not always pick the same one, or a per-guild "who's in voice" tiebreak will visibly
  favor one user). Feed the result into a small Gemini call at **priority=2** (background —
  never contend with `/ask`), reusing `build_chat_prompt`'s `memories=` parameter
  (`personality/prompts.py:133-180`) with a new scenario string like "volunteer one
  unprompted callback line, referencing the memory below, to no one in particular — you're
  just talking". Post via `_resolve_dexter_channel` (`bot.py:101-141`), same
  `allowed_mentions=discord.AllowedMentions.none()` discipline as every other ambient post.
  If `recall()` returns `[]` (nothing above the similarity floor for a generic anchor —
  likely, since there's no specific query text), **skip the post entirely** rather than
  falling back to a generic line; a proactive callback with no memory to reference isn't a
  callback, it's just noise indistinguishable from the loneliness message that already
  exists.

### (e) Vision / multimodal roasting

- **New cog: `cogs/vision.py`**, not an extension of `cogs/events.py::on_message`. Rationale:
  this codebase already resolved the identical fork once — image *generation* is its own
  `cogs/imagine.py`, separate from `cogs/ai.py`, even though both are Gemini text/prompt
  flows. Vision (image *understanding*) is the same shape of decision: its own feature
  domain, its own cooldown/cadence state, its own content-safety gate — bolting it onto
  `events.py::on_message` (already handling message-buffer feeding + reactions + thanks
  detection) would tangle three unrelated concerns in one already-dense listener. discord.py
  supports multiple cogs registering `on_message` listeners without conflict (both fire),
  so this costs nothing structurally.
- **Image bytes fetch:** `discord.Attachment.read()` — built into discord.py, no new HTTP
  client needed. In `on_message`: filter
  `message.attachments` for `a.content_type and a.content_type.startswith("image/")`, then
  `image_bytes = await attachment.read()`; pass `attachment.content_type` through as the
  MIME type.
- **New `GeminiService` method** (`services/gemini.py`), verified against the current
  `google-genai` Python SDK via Context7 (`/googleapis/python-genai`):
  ```python
  async def describe_image(
      self, image_bytes: bytes, mime_type: str, prompt: str, priority: int = 2,
  ) -> str | None:
      await self._rate_limiter.acquire(priority)   # SAME 15 RPM budget as chat() — no new limiter
      response = await self._client.aio.models.generate_content(
          model=config.GEMINI_MODEL,                # gemini-2.5-flash — vision-capable, confirmed via Context7
          contents=[
              types.Content(role="user", parts=[
                  types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                  types.Part.from_text(text=prompt),
              ]),
          ],
          config=types.GenerateContentConfig(system_instruction=system_prompt),
      )
      ...
  ```
  Confirmed API shape (Context7, `googleapis/python-genai`, `docs/index.html` +
  `google/genai/types.py`): `types.Part.from_bytes(data=..., mime_type=...)` combined with a
  text `Part` inside one `types.Content`, passed to `generate_content` — the same call shape
  `chat()` already uses (`services/gemini.py:189-196`), just with an image `Part` appended.
  **Shares `self._rate_limiter`** (the existing 15 RPM chat/image budget), never
  `self._embed_limiter` — matches the milestone framing ("draws on the shared 15 RPM
  budget"). Use **priority=2** (background/ambient — mirrors `_generate_ambient_roast`'s
  priority=2 Gemini calls in `cogs/events.py:154`), since vision roasting is unprompted
  ambient behavior, not a user-invoked command; it must never starve `/ask`.
  Reuse the existing `GeminiRefusalError` exception (already defined at
  `services/gemini.py:27-28` but currently unused — `generate_image` just returns `None` on
  an empty response instead of raising it) as the vision content-safety signal path, or at
  minimum treat an empty/refused response the same way `generate_image` already does
  (`services/gemini.py:240-248`).
- **Cadence + safety gating:** new pure function, `logic/vision.py:decide_vision_roast(...)`
  (new small module — this isn't a natural extension of `logic/roasts.py`'s ambient-roast
  gates since it has a different trigger shape — image-presence rather than
  voice-state/message-content), taking a chance roll + per-channel/user cooldown (new
  `config.VISION_ROAST_CHANCE`, `config.VISION_ROAST_COOLDOWN_SECONDS`), mirroring
  `cooldown_elapsed`/`decide_ambient_roast`'s structure exactly. Designated-channel-only
  applies here too (Critical Rule 9 / CLAUDE.md) — reuse `_get_ambient_channel`-style
  resolution to confirm the message's channel is the ambient/music channel before reacting,
  or explicitly gate to `config.DEXTER_CHANNEL_ID` only (stricter — recommended, since an
  unprompted image roast in an arbitrary channel is a bigger blast-radius mistake than a
  voice-join roast). VIS-01/02 content-safety guardrails: rely primarily on Gemini's own
  safety filtering (empty/refused response → silently skip, never retry, never post a
  fallback template — unlike ambient roasts, there's no safe generic fallback for "describe
  this image sarcastically" when the model has refused), plus a hard content-type allowlist
  (`image/png`, `image/jpeg`, `image/webp`, `image/gif` — reject anything else without
  calling Gemini at all) and an attachment-size ceiling before ever reading bytes.

## New Components

| Component | Type | Location | Depends on |
|---|---|---|---|
| Taste memory kinds | Config extension | `config.py: MEMORY_SALIENCE_BASE_WEIGHTS` | none |
| `taste_distill_batch` | `@tasks.loop` | `bot.py` (module scope) | `MemoryService`, `song_history`/`user_artist_counts` |
| Artist play/skip aggregate helper(s) | DB helper(s) | `database.py` | `song_history`, `user_artist_counts` (existing tables) |
| `logic/taste.py` | Pure logic module | new file | none (pure) |
| `services/taste.py` (`TasteService`) | Service | new file | pool, `GeminiService`, `MemoryService`, `logic/taste.py`, new DB helpers |
| `/discover`-style taste-graph command | Slash command | `cogs/ai.py` or new `cogs/discover.py` | `TasteService` |
| Generative jam suggestion path | Cog logic | `cogs/library.py` (jam save/add flow) or `cogs/ai.py` | `TasteService` |
| `proactive_callback` | `@tasks.loop` | `bot.py` (module scope) | `MemoryService`, `bot.voice_clients`, `_resolve_dexter_channel` |
| `decide_proactive_callback` | Pure logic fn | `logic/roasts.py` (extend) | none (pure) |
| `/memory` inspect/forget command | Slash command | new `cogs/memory.py` or added to `cogs/library.py` | `MemoryService`, new DB helpers (list/delete by user) |
| `cogs/vision.py` | New cog | new file | `GeminiService.describe_image`, `logic/vision.py` |
| `GeminiService.describe_image()` | Service method | `services/gemini.py` (extend) | existing `self._rate_limiter` (no new limiter) |
| `logic/vision.py` (`decide_vision_roast`) | Pure logic module | new file | none (pure) |
| Vision prompt builder | Prompt fn | `personality/prompts.py` (extend) | none (pure) |

## Modified Components

| File | Change |
|---|---|
| `config.py` | New `MEMORY_SALIENCE_BASE_WEIGHTS` keys (`taste_episode`, etc.); new `PROACTIVE_CALLBACK_*`, `VISION_ROAST_*` knobs; new `TASTE_*` tuning knobs (mirrors Phase 11's `MEMORY_*` and Phase 12's `AUTO_QUEUE_SEARCH_CANDIDATES`-style additions) |
| `database.py` | New structured aggregate helper(s) for artist play/skip counts; new helpers for `/memory` (list a user's memories, delete-by-id scoped to `user_id`) |
| `bot.py` | Two new `@tasks.loop` functions (`taste_distill_batch`, `proactive_callback`) with `.before_loop`/`.error` pairs; both added to `_cleanup_partial_init`'s stop-list (`bot.py:280-281`) and the start-guard block (`bot.py:446-460`); `TasteService` wired in `_initialize_once` next to `MemoryService` (`bot.py:415-418`); new module-level cooldown dict for proactive callbacks |
| `logic/roasts.py` | New `decide_proactive_callback()` pure function, sibling of `decide_ambient_roast` |
| `cogs/ai.py::try_auto_queue` | Insert a `TasteService`/`logic/taste.py` scoring pass into the per-suggestion loop (`cogs/ai.py:311-364`) so skip-weighted artists are deprioritized before the existing `validate_youtube_match` check, not instead of it |
| `personality/prompts.py` | New prompt builder(s) for taste-graph recommendations (parallel to `build_recommendation_prompt`) and for the proactive-callback / vision-roast scenario text |
| `services/gemini.py` | New `describe_image()` method, reusing `self._rate_limiter` |
| `services/memory.py` | **No code change required** — kind-agnostic by design; only the caller-supplied `kind` string and `config.MEMORY_SALIENCE_BASE_WEIGHTS` lookup change |
| `models/memory.py` | **No code change required** for the memory-kind extension itself; may need a `decay_predicate` review if new kinds want different decay tiers (currently governed by `salience`, already ordinal) |

## Data Flow

### Taste memory write (new)

```
song_history + user_artist_counts (existing tables)
    ↓ (daily, taste_distill_batch @tasks.loop in bot.py)
raw-text per-user summary (top artists, binges — NO counts embedded)
    ↓
MemoryService.distill_and_remember(kind="taste_episode", ...)   [UNCHANGED service code]
    ↓ distill() LLM pass + is_sensitive/contains_number backstop [UNCHANGED]
    ↓ remember() embed + dedup + cap-evict                        [UNCHANGED]
user_memories row (kind="taste_episode")
```

### Taste memory read — qualitative (existing pipe, new content)

```
/roast, /ask, ambient roast, (new) proactive_callback, (new) jam-generation flavor
    ↓
MemoryService.recall(user_id, guild_id, anchor)   [UNCHANGED — kind-agnostic]
    ↓ ANN + floor + rerank + cap                    [UNCHANGED]
list[str] facts — now may include taste_episode facts alongside milestone/daily_batch/etc.
    ↓
build_chat_prompt(..., memories=facts)              [UNCHANGED]
```

### Taste signal read — structured (new path, for auto-queue ranking)

```
song_history.was_skipped + user_artist_counts.play_count
    ↓ (new database.py helper, per guild/user)
services/taste.py: TasteService.get_taste_profile()
    ↓
logic/taste.py: compute_artist_affinity()  [pure, unit-tested]
    ↓
cogs/ai.py: try_auto_queue() candidate loop — deprioritize/filter before validate_youtube_match
```

### Proactive callback (new)

```
bot.py: idle_check (existing, 60s loop) marks vc._loneliness_posted = True
    ↓ (state read, not re-derived)
bot.py: proactive_callback (new, ~10-15 min loop)
    ↓ decide_proactive_callback(chance_roll, cooldown, quiet_and_occupied) → bool
    ↓ (if True) pick one human member of a quiet occupied VC
MemoryService.recall(member_id, guild_id, generic_anchor)   [UNCHANGED]
    ↓ [] → skip entirely; non-empty → continue
Gemini chat(priority=2) with a "volunteer this unprompted" scenario
    ↓
_resolve_dexter_channel(guild).send(...)
```

### Vision (new)

```
cogs/vision.py: on_message(message)
    ↓ filter: attachments with image/* content_type, in designated channel
decide_vision_roast(chance_roll, cooldown_elapsed) → bool   [new pure fn, logic/vision.py]
    ↓ (if True)
attachment.read() → image_bytes                              [discord.py built-in]
    ↓
GeminiService.describe_image(image_bytes, mime_type, prompt, priority=2)   [new method]
    ↓ shares self._rate_limiter (15 RPM) — NOT self._embed_limiter
response text (or None/refusal → skip silently, no fallback template)
    ↓
message.channel.send(response)
```

## Suggested Build Order

Foundation before consumers, structured-data plumbing before AI orchestration, low-risk
extensions before new cogs:

1. **Taste memory foundation** — `config.py` new `MEMORY_SALIENCE_BASE_WEIGHTS` keys +
   new structured `database.py` aggregate helper(s) (artist play/skip counts) + new
   `taste_distill_batch` `@tasks.loop` in `bot.py`. This is the "retrievable substrate"
   the milestone brief names explicitly as the foundation phase; everything else reads
   from it. Ship this first and let it run for at least a day of real usage before building
   consumers, so there's actual `taste_episode` data to validate recall/scoring against
   (mirrors the Phase 11 pattern of a live-Neon spike before retrieval landed).
2. **`logic/taste.py` (pure, TDD)** — `compute_artist_affinity`, novelty filtering, ranking.
   No dependencies beyond the new DB helpers' return shape. Build and unit-test this before
   `services/taste.py` exists, same as `logic/autoqueue.py` predates its cog integration.
3. **`services/taste.py` (`TasteService`)** — wires `logic/taste.py` + the new DB helpers +
   `GeminiService` + `MemoryService`. Wire into `bot.py:_initialize_once` immediately after
   `MemoryService` construction.
4. **Smarter auto-queue** — extend `cogs/ai.py::try_auto_queue`'s suggestion loop to call
   `TasteService`/`logic/taste.py` scoring before `validate_youtube_match`. This is the
   first real consumer and validates the whole taste pipeline end-to-end on existing,
   well-understood code.
5. **Taste-graph discovery command + generative jams** — second and third consumers of
   `TasteService`, built once step 4 has proven the service contract works.
6. **RAG into `/roast` + `/ask`** — effectively free once step 1 is live (facts flow through
   the unchanged `recall()` pipe); this step is really "verify it's landing well, tune
   `MEMORY_CALLBACK_CHANCE`/weights for the new kind if needed," not new plumbing.
7. **`/memory` inspect/forget command** — new DB helpers (list/delete-by-id scoped to
   `user_id`) + a small new or extended cog. Independent of steps 2-6; can be built any time
   after step 1, but sequenced here because it's a good place to validate that the new
   `taste_episode` facts are sane before they start feeding autonomous behavior (proactive
   callbacks) in step 8.
8. **Proactive callbacks** — depends on `MemoryService.recall()` having *something* worth
   surfacing (steps 1+6 validated), plus `idle_check`'s loneliness state (already live).
   New `decide_proactive_callback` pure fn first (TDD), then the `bot.py` loop.
9. **Vision** — fully independent of steps 1-8 (no taste-memory dependency); can be built in
   parallel with the taste-brain track if desired, but sequenced last here because it is the
   highest-blast-radius new surface (unprompted content generation from arbitrary user
   images) and benefits from the content-safety gating patterns (refusal handling, cadence
   gates) being freshly proven out by proactive callbacks in step 8. Order internally:
   `logic/vision.py` (pure, TDD) → `GeminiService.describe_image()` → `cogs/vision.py`.

**Dependency graph in one line:** `taste memory foundation → logic/taste.py → services/taste.py
→ {auto-queue, discovery command, jams} → (parallel) RAG-into-roast/ask (free) + /memory
command → proactive callbacks → vision (independent, sequenced last for risk reasons)`.

## Testability (logic/ seam) per new piece

| New pure logic | Module | Inputs are primitives? | Notes |
|---|---|---|---|
| `compute_artist_affinity` | `logic/taste.py` | Yes — `dict[str,int]` play/skip counts | Highest-value test target; branchy scoring arithmetic is exactly the Phase-10 scar pattern |
| `filter_recent_repeats` / `rank_discovery_candidates` | `logic/taste.py` | Yes — lists of dicts/dataclasses | |
| `decide_proactive_callback` | `logic/roasts.py` | Yes — chance_roll, cooldown seconds, bools, mirrors `decide_ambient_roast` exactly | |
| `decide_vision_roast` | `logic/vision.py` | Yes — chance_roll, cooldown seconds | |
| `taste_distill_batch`, `proactive_callback`, `cogs/vision.py::on_message`, `TasteService`, `GeminiService.describe_image` | glue (bot.py / services / cogs) | N/A | Untested-by-design per this codebase's convention — Discord/process glue verified by clean boot + structural review, not mocked tests |

## Sources

- Direct reads (HIGH confidence, this codebase): `bot.py`, `services/memory.py`,
  `services/gemini.py`, `models/memory.py`, `database.py`, `cogs/ai.py`, `cogs/events.py`,
  `cogs/library.py`, `logic/autoqueue.py`, `logic/roasts.py`, `personality/prompts.py`,
  `models/user_profile.py`, `utils/tasks.py`, `config.py`, `.planning/PROJECT.md`.
- Context7 (HIGH confidence, verified 2026-07-02): `/googleapis/python-genai` —
  `types.Part.from_bytes(data=..., mime_type=...)` API shape for multimodal image input,
  confirming the vision integration pattern proposed for `GeminiService.describe_image()`.

---
*Architecture research for: Dexter v1.3 "Taste Brain" milestone*
*Researched: 2026-07-02*
