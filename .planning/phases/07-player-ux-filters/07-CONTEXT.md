# Phase 7: Player UX & Filters - Context

**Gathered:** 2026-06-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 7 delivers **full interactive playback control + audio effects + personal saves** for Dexter:

1. **Control buttons** on the now-playing embed (PLAYER-01)
2. **`/seek`, `/previous`, `/jump`** navigation commands (PLAYER-02/03/04)
3. **Favorites** — save the current song, retrieve later (PLAYER-05)
4. **Playlists** — save the queue as a named snapshot, load it back (PLAYER-06)
5. **`/filter`** audio-effect presets + `/filter off` (PLAYER-07/08)

It does NOT add new audio sources, `/volume`, prefix/hybrid commands, or a web dashboard
(all locked Out of Scope). It clarifies HOW to build the eight PLAYER-* requirements; it does
not expand them.

</domain>

<decisions>
## Implementation Decisions

### Control Buttons (PLAYER-01)
- **D-01:** The now-playing embed carries exactly the **5 core buttons** — play/pause, skip, loop-toggle, shuffle, stop. No favorite or queue button this phase.
- **D-02:** Access = **anyone currently in the bot's voice channel**. Users not in the call get an ephemeral refusal. Not requester-locked; not open to the whole text channel.
- **D-03:** Implemented as a **persistent view** (`timeout=None` + stable `custom_id`s, re-registered via `bot.add_view()` in `on_ready`) so the buttons survive a bot restart and never go dead mid-track. This is a deliberate departure from the existing *timed* views.
- **D-04:** A button press **silently re-renders the now-playing embed** to reflect new state (paused, loop mode, etc.) — no public per-press chatter. The interaction MUST be acked (e.g. `interaction.response.edit_message`) to avoid Discord "interaction failed".
- **D-05:** The loop button **cycles off → single → queue → off**; its label/emoji reflects the active `LoopMode`.
- **D-06:** The stop button is **immediate** — clears the queue + leaves voice, identical to `/stop`. No confirm step.

### Audio Filters (PLAYER-07 / PLAYER-08)
- **D-07:** Presets = **bassboost, nightcore, slowed+reverb, 8d** (the four named); `/filter off` clears. Input is a **fixed-choices dropdown** (`app_commands.Choices`) that includes `off`.
- **D-08:** A filter is **whole-playback**, not per-user — there is one voice stream per guild. Stored as **guild-level active-filter state**.
- **D-09:** Applying / changing / clearing a filter **resumes from the current position** (not a restart from 0:00), reusing the same elapsed-tracking + FFmpeg `-ss` re-encode machinery as `/seek`.
- **D-10:** An active filter is **sticky** — it stays on for the current track and all subsequent tracks until `/filter off`. The per-track source builder checks the guild active-filter to pick the path. (This implements the ROADMAP "per-track `active_filter` flag".)
- **D-11:** **One preset at a time** — `/filter <preset>` replaces whatever is active; no stacking.
- **D-12:** **Opus-copy / passthrough is the default path** (already true for cache hits via `FFmpegOpusAudio`); a **transcode is taken ONLY when a filter (or a seek) is active** for that track. Do NOT remove the passthrough path. This honors the ROADMAP filter-vs-opus-copy design note and does **not** require Phase 6 — the passthrough already exists for cached tracks.
- **D-13:** The now-playing embed **surfaces the active filter** when one is set.

### Navigation — /seek, /previous, /jump (PLAYER-02/03/04)
- **D-14:** `/seek` accepts **`mm:ss`, `h:mm:ss`, and raw seconds** (e.g. `1:30` or `90`).
- **D-15:** Seeking **past the end → advance to the next track** (reuse skip/advance logic), rather than clamping or erroring.
- **D-16:** `/seek` shares the FFmpeg `-ss` re-encode path with filters; it must work on cached, downloaded, and filtered tracks. (Exact source-rebuild mechanics → research/planning.)
- **D-17:** `/previous` and `/jump` build on the existing **no-pop `current_index` model** — `MusicQueue.previous()` already exists; `/jump <n>` sets `current_index`. (Mechanics → research/planning.)

### Favorites (PLAYER-05)
- **D-18:** Favorites are **per-user and global** (keyed by `user_id` only) — they follow the user across servers.
- **D-19:** `/favorite` saves the **currently-playing song only** (no search/URL argument this phase).
- **D-20:** `/favorites` returns a **pick-list select menu** (reuse the `SongSelect` pattern); picking queues that song. Removal is handled **within the picker** — no separate command.
- **D-21:** Cap = **25 favorites per user** (fits a single Discord select menu, no pagination). Over-cap saves get an ephemeral personality error.
- **D-22:** New Postgres table (e.g. `user_favorites`) added to `SCHEMA_SQL` via `CREATE TABLE IF NOT EXISTS`.

### Playlists (PLAYER-06)
- **D-23:** A playlist is a **frozen snapshot** of the queue's track list at save time — reuse the `guild_queues` JSONB pattern (`Track.to_dict()` / `from_dict()`).
- **D-24:** Playlists are **per-user** (keyed `user_id` + `name`); only the owner loads them.
- **D-25:** Command surface is a **group: `/playlist save|load|list|delete`**.
- **D-26:** Load **appends** the snapshot to the current queue (non-destructive; on an empty queue it just starts playing). Respects `MAX_QUEUE_SIZE_PER_GUILD` (500) — truncate + inform on overflow.
- **D-27:** Name clash on save = **overwrite / upsert**, keyed `(user_id, name)`.
- **D-28:** Cap = **25 playlists per user** (parallel to favorites); tracks per playlist are bounded by the 500 queue cap. New Postgres table (e.g. `user_playlists`) in `SCHEMA_SQL`.

### Cross-cutting — Personality & Error States
- **D-29:** All new user-facing text uses **Dexter's voice** — lowercase, dry, one-emoji-max — via `personality/responses.py` template pools with a guaranteed fallback. Gemini is not required for these; templated lines are fine.
- **D-30:** Error / empty-state / no-op responses are **ephemeral** (only the actor sees them); successful public actions (now-playing) stay public.

### Claude's Discretion
Left to research/planning, consistent with the decisions above:
- Exact table/column names and indexes for `user_favorites` / `user_playlists`.
- `custom_id` scheme for the persistent button view.
- The FFmpeg filter-chain strings per preset (`bass=g=`, `atempo`/`asetrate`, `aecho`, `apulsator`, etc.).
- `/seek` time-string parser implementation.
- Select-menu removal UX for `/favorites`.
- Whether a tiny ephemeral "saved." / "removed." confirmation is added on save/remove.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` — Phase 7 entry: goal, the 5 success criteria, and the **filter-vs-opus-copy design note** (per-track `active_filter` flag; opus-copy default, transcode only when filtered).
- `.planning/REQUIREMENTS.md` — **PLAYER-01 … PLAYER-08** (the 8 requirements this phase satisfies) + the locked Out-of-Scope list (`/volume`, prefix commands, non-YouTube sources, web dashboard).
- `CLAUDE.md` — build spec: slash-command-only convention, personality rules (lowercase / one-emoji-max / accuracy-first), FFmpeg/voice cleanup-on-error, `MAX_QUEUE_SIZE_PER_GUILD`, asyncpg `SCHEMA_SQL` pattern, music pipeline + playback-engine gotchas.

### Code Phase 7 builds on
- `models/queue.py` — `Track` (`to_dict`/`from_dict` JSONB serialization), `MusicQueue` (no-pop `current_index` model, `previous()`, `shuffle()` upcoming-only, `loop_mode`, `_play_generation`, `_now_playing_message_id`, existing `auto_lyrics` flag).
- `services/audio.py` — `AudioService.get_source` (3-tier cache→download→stream; opus passthrough via `FFmpegOpusAudio`). The seek/filter re-encode path attaches here.
- `utils/embeds.py` — `now_playing()` embed builder (where the button view + active-filter line attach) and brand colors.
- `cogs/music.py` — playback engine + the 4 existing `discord.ui.View` patterns (`SongSelectView`, `QueuePageView`, `LyricsPageView`, `HistoryPageView`); now-playing post/edit sites (~407, ~565, ~899); all command handlers (~767–1144).
- `database.py` — `SCHEMA_SQL` + asyncpg helper pattern for new `user_favorites` / `user_playlists` tables; `guild_queues` JSONB persistence as the playlist-snapshot analog.
- `services/queue_persistence.py` — Phase-4 queue JSONB persist/restore — the closest analog for playlist snapshot save/load.
- `utils/formatters.py` — `format_duration` / `progress_bar` (seek + now-playing rendering).
- `personality/responses.py` — templated response pools (home for new command / error / no-op lines).
- `config.py` — central settings (new constants: filter preset map, favorites/playlist caps).

> **Staleness note:** `.planning/codebase/*.md` maps are dated 2026-06-01 and predate the Phase-4 SQLite→PostgreSQL migration. Treat `CLAUDE.md` + actual source as authoritative on persistence (asyncpg, not aiosqlite).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`discord.ui.View` + `@discord.ui.button`** is already used 4× — the control-button view follows this, but as a **persistent** view (`timeout=None` + `custom_id` + `bot.add_view()` in `on_ready`), unlike the existing timed views.
- **`SongSelect` dropdown** → reuse for the `/favorites` pick-list.
- **`Track.to_dict()`/`from_dict()` + `guild_queues` JSONB** → reuse for playlist snapshots.
- **`MusicQueue.previous()`** already exists; the `current_index` model makes `/jump` a one-line index set; `shuffle()` already shuffles upcoming-only.
- **`AudioService.get_source`** already does opus passthrough for cache hits — i.e. the "opus-copy default" already holds for cached tracks; filters add a transcode branch, they do not replace it.

### Established Patterns
- All commands are `app_commands` slash commands; cogs reach services via `self.bot.*`; all settings live in `config.py`; new persistence goes in `SCHEMA_SQL` with async helpers.
- The now-playing embed is a **single persisted message** (`queue._now_playing_message_id`) edited on track change — the buttons live on this message.
- Personality output = Gemini-first with a guaranteed template fallback; lowercase, one-emoji-max.

### Integration Points
- **Buttons** attach to the `now_playing()` embed message in `cogs/music.py` (`_on_track_end` ~407, initial post ~565/~899); the persistent view is registered in `bot.py` `on_ready` via `bot.add_view()`.
- **Seek/filter re-encode** attaches in `services/audio.py` `get_source` — needs `before_options` `-ss` + an `-af` filter chain, and a non-passthrough source whenever the track is seeked or filtered.
- **New tables** init in `database.py` `SCHEMA_SQL`; helpers added alongside the existing ones.
- **`config.py`** gains new constants (preset definitions, favorites/playlist caps).

</code_context>

<specifics>
## Specific Ideas

- The filter "from current position" behavior **deliberately shares machinery with `/seek`** — build seek's elapsed-tracking + `-ss` source rebuild first, then filters reuse it. Plan these two together.
- The stop button must behave **identically to `/stop`** (immediate clear + leave) for consistency.
- Persistent buttons must **ack every interaction** (e.g. `edit_message`) — un-acked presses surface as Discord "interaction failed".

</specifics>

<deferred>
## Deferred Ideas

Considered during discussion, intentionally out of this phase:

- **❤ favorite button** and **queue-view button** on the now-playing embed (kept to the 5 core buttons this phase).
- **`/filter` stacking / combinable effects** (one-at-a-time chosen).
- **Relative seek** (`+30` / `-10`) for `/seek` (mm:ss + raw seconds chosen).
- **Server-shared / communal playlists** and **living (editable) playlists** (per-user frozen snapshot chosen).
- **Favoriting by search/URL** rather than current-song-only.
- **Explicit `/favorites remove` command** and **confirm-on-stop** (handled in-picker / immediate, respectively).

None of these are roadmap items — capture for a future milestone if desired.

## Sequencing note (for the planner)
Phase 7's ROADMAP dependencies are Phase 5 (live deploy — **PARKED**) and Phase 6 (opus-copy — **NOT started**). **Neither blocks Phase 7 implementation:** button interaction is testable on the on-demand local run (residential IP), and the filter/transcode split is buildable now because opus passthrough already exists for cached tracks (D-12). Do not block planning on Phase 5/6.

</deferred>

---

*Phase: 7-Player UX & Filters*
*Context gathered: 2026-06-19*
