# Phase 12: Richer Music/UX - Context

**Gathered:** 2026-06-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Round out the existing v1.1 music/social surfaces with four already-scoped features —
no new capabilities beyond these:

1. **UX-01** — Per-server shared playlists ("jams"), distinct from the existing user-global favorites/playlists.
2. **UX-02** — Surface the already-tracked skip-rate analytics to users.
3. **UX-03** — A third `/lyrics` fallback source so it degrades gracefully when both Genius and AZLyrics fail.
4. **UX-04** — Validate AI auto-queue suggestions against actual YouTube results, rejecting hallucinated tracks before queueing.

This phase clarifies HOW to implement these four — it does not add a fifth feature.
</domain>

<decisions>
## Implementation Decisions

### UX-01 — Per-server playlists ("jams")
- **D-01:** New dedicated **`/jam` command group** (`save`/`add`/`load`/`list`/`delete`), kept clearly distinct from the existing user-global `/playlist` group. Mental model: `/playlist` = yours, `/jam` = the server's.
- **D-02:** Jams are **guild-scoped** — keyed by `guild_id` (not `user_id`). New table mirroring `user_playlists` but PK'd on guild + name (e.g. `guild_jams`).
- **D-03:** **Anyone in the server can edit** a jam — save/overwrite/append/delete, no role or creator checks. Collaborative "shared community mixtape" model. (No `created_by` permission gate.)
- **D-04:** **Interaction model A — stored named list, no session.** A jam is just a named server-owned collection; there is nothing to "get out of." `/jam add` appends the now-playing song to a named jam; `/jam load <name>` dumps that jam into the live queue (same enqueue path as `/playlist load`); `/jam list` / `/jam delete` manage them. Explicitly NOT a stateful `/jam start`…`/jam stop` session mode (that's deferred — see Deferred Ideas).
- **D-05:** Reuse existing patterns — ephemeral responses, a per-guild jam cap, and the name-length cap (mirror `PLAYLIST_NAME_MAX_LENGTH` / the playlist cap logic in `cogs/library.py`). Add a `JAMS_PER_GUILD_MAX`-style config knob alongside the existing playlist caps.

### UX-02 — Skip-rate analytics
- **D-06:** Surface via a **dedicated `/skips` command** (its own embed), NOT folded into `/stats` — keeps `/stats` ops-flavored and gives skip analytics room for a leaderboard + roast caption.
- **D-07:** Show **both**: lead with the **server's most-skipped songs** (reuse the existing `most_skipped` query at `database.py:447`), plus the **requesting user's personal skip rate** as a roastable footer ("you skip X% of what you queue").
- **D-08:** **Min-plays floor** to avoid noisy "100% (1/1)" stats — a song/user skip rate only displays once it has ≥ N data points. Add a `SKIP_STATS_MIN_PLAYS` config knob (default 5); below that, omit or label "not enough data."
- **D-09:** **All-time window** — aggregate over all of `song_history`, no rolling date filter. Simplest query, fits existing patterns; revisit only if it gets stale.

### UX-03 — Third lyrics fallback
- **D-10:** Add **LRCLIB** (`lrclib.net`) as the **third** source in the existing chain: Genius → AZLyrics → **LRCLIB**. Free, no API key, clean JSON API, purpose-built for music players (robust, no scrape fragility).
- **D-11:** Use LRCLIB's **`plainLyrics`** field (not `syncedLyrics`). Slot it into the existing `LyricsService.get_lyrics()` fallback chain in `services/lyrics.py`, following the same async/timeout/byte-cap and pure-helper conventions as the Genius/AZLyrics paths.

### UX-04 — Auto-queue hallucination validation
- **D-12:** Validate Gemini suggestions with a **fuzzy title+artist match** against the YouTube result. Normalize both sides (lowercase, strip punctuation and noise tokens like "official video"/"official audio"/"lyrics"/"(HD)"), then require the result title to fuzzily contain BOTH the suggested title AND artist. Tolerates YouTube title noise while rejecting clear mismatches.
- **D-13:** **Widen the search** — bump `async_search` count from 1 to ~3 (a `AUTO_QUEUE_SEARCH_CANDIDATES`-style knob) and pick the **first result that passes** the fuzzy check, rather than validating only the single top hit. Robust against a bad #1.
- **D-14:** On rejection (no candidate passes for a suggestion), **try the next Gemini suggestion** to keep the round full — still capped at `AUTO_QUEUE_SONGS_PER_ROUND`. The round may come up short only if suggestions are exhausted. Implement in the loop at `cogs/ai.py:307`.

### Claude's Discretion
- Exact per-guild jam cap value and the `SKIP_STATS_MIN_PLAYS` / `AUTO_QUEUE_SEARCH_CANDIDATES` defaults (planner/researcher to pick sensible values; min-plays ≈ 5, search candidates ≈ 3 as starting points).
- The specific fuzzy-matching implementation (substring containment vs token-set ratio / `difflib`); keep it a pure, importable, unit-testable helper per the Phase 10 `logic/` convention.
- LRCLIB request shape (exact `/api/get` match vs `/api/search`) — pick whichever gives reliable plain-lyrics hits with the title/artist Dexter already has.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase definition & requirements
- `.planning/ROADMAP.md` §"Phase 12: Richer Music/UX" — goal, success criteria, the 4 plan stubs (12-01..12-04).
- `.planning/REQUIREMENTS.md` §"Richer Music / UX (Phase 12)" — UX-01..UX-04 acceptance wording.

### Existing code to extend (not external specs — in-repo anchors)
- `cogs/library.py` — existing user-global `/favorite`, `/favorites`, `/playlist save|load|list|delete`; the `/jam` group mirrors this (caps, ephemeral, name-length guards at ~line 424+).
- `database.py` §`user_favorites` / `user_playlists` (lines 146–169) — schema pattern the new `guild_jams` table mirrors; `most_skipped` query at line 447 (reuse for `/skips`); `was_skipped` column (line 108).
- `services/lyrics.py` — `LyricsService` Genius→AZLyrics chain + pure helpers; LRCLIB slots in as the third link.
- `cogs/ai.py` §`try_auto_queue` (lines 254–400, suggestion loop at 307) — where UX-04 validation lands.
- `cogs/ops.py` §`/stats` (lines 147+) — referenced as the *rejected* surface for skip-rate (kept distinct via `/skips`).

No external ADRs/specs — requirements fully captured in the decisions above and the in-repo anchors.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `cogs/library.py` `/playlist` group + cap/ephemeral/name-length guards — direct template for the new `/jam` group (swap `user_id` keying for `guild_id`).
- `database.py` `save_playlist`/`get_playlist`/`list_playlists`/`delete_playlist`/`count_playlists` helpers + `user_playlists` JSONB snapshot schema — mirror for `guild_jams` storage helpers.
- `database.py:447` `most_skipped` query + `song_history.was_skipped` — the skip data UX-02 surfaces already exists; no new tracking needed.
- `services/lyrics.py` fallback-chain structure + pure importable helpers (timeout, byte-cap, sanitize) — LRCLIB follows the same shape.
- `cogs/ai.py:307` auto-queue search→extract→queue loop — currently trusts the top YouTube hit blindly; UX-04 inserts the validation gate here.

### Established Patterns
- Phase 10 `logic/` convention: extract decision logic (fuzzy match, skip-rate aggregation, min-plays gating) into pure, importable, unit-tested functions; keep Discord glue thin.
- Ephemeral responses + per-user/per-guild caps + config-driven thresholds (`config.py`) for all library/ops surfaces.

### Integration Points
- New `guild_jams` table added to `SCHEMA_SQL` (idempotent `CREATE TABLE IF NOT EXISTS`).
- `/jam load` reuses MusicCog's enqueue path (same as `/playlist load`).
- LRCLIB call added inside `LyricsService.get_lyrics()` after AZLyrics returns nothing.
- New config knobs: `JAMS_PER_GUILD_MAX` (and jam name length, or reuse `PLAYLIST_NAME_MAX_LENGTH`), `SKIP_STATS_MIN_PLAYS`, `AUTO_QUEUE_SEARCH_CANDIDATES`.
</code_context>

<specifics>
## Specific Ideas

- Skip footer should be roast-flavored, in Dexter's lowercase/dry voice ("you skip X% of what you queue. bold of you to keep going.").
- Jam is explicitly a "server mixtape that grows over time" — collaborative, low-friction, no ownership friction and nothing to get trapped inside.
</specifics>

<deferred>
## Deferred Ideas

- **Active "jam session" mode** (`/jam start` → server enters jam mode, auto-collecting queued songs → `/jam stop`). Stateful, more edge cases (concurrent starters, restart mid-jam) — closer to its own phase. Deferred in favor of the stored-named-list model (D-04).
- **Rolling time-window / re-rollable skip leaderboards** (last-N-days) — deferred in favor of all-time (D-09); revisit if all-time stats stagnate.
- **Per-jam edit permissions / ownership** (creator-or-admin-only) — deferred; current model is fully open (D-03).

None of the above expanded this phase's scope — discussion stayed within UX-01..UX-04.
</deferred>

---

*Phase: 12-richer-music-ux*
*Context gathered: 2026-06-30*
