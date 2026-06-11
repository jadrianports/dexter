# Phase 3: Alive - Context

**Gathered:** 2026-06-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 makes Dexter feel *present* — it reacts, roasts unprompted, tracks habits, and exposes lyrics and history. Concretely:

- **Unprompted roasts:** voice-join/leave (30% / 5-min cooldown), late-night 1–5am (50%), same-song-3+×/day (always), channel-move complaint (always)
- **Reactions:** 👀 on YouTube/Spotify links, 🫡 on "goodnight"/"gn", 😐 on bare mention, deflecting-warmth text on "thanks"
- **Expanded seasonal awareness** injected by date
- **Status rotation** every 5 min, **startup message** on boot, **idle-loneliness** message after 30+ min silence with humans in voice
- **Streak tracking** (consecutive days) + **milestone roasts** (songs 100/250/500/1000; streak-days 7/14/30/60/100)
- **`/lyrics`** (Genius primary → AZLyrics fallback, paginated) and **`/history`** (recently queued songs, server-wide)

Requirements: PERS-02…09, LYRIC-01, HIST-01.

**Out of scope (clarifies, does not expand):** No new music/AI capabilities; no multi-server/scale work (Phase 4); no hosting decision (Phase 4).
</domain>

<decisions>
## Implementation Decisions

### Voice calibration (THE foundational decision — drives all roast content)
- **D-01:** Dexter's voice is **arrogant, superior, dry, contemptuous** — he is certain he has better taste than everyone in the server. The humor comes from **specific recall of the user's tracked behavior** (real song title / artist / play-count), not from generic quips.
- **D-02:** **Contempt is aimed OUTWARD and DOWN at users only.** Three **permanently banned inward modes:**
  1. **Bot self-awareness / fourth-wall** ("i'm just software", "i could've been a calculator") — *cringe, do not use*
  2. **Pop-psych** — diagnosing the user's psyche ("what does this say about you", "cry for help") — *try-hard, do not use*
  3. **Self-deprecation / low self-esteem** — lonely, unappreciated, fishing for thanks ("did you miss me, probably not") — *Dexter roasts users, never himself*
- **D-03:** **Language = mild swearing** (damn, hell, crap, ass, screw). **No f-bombs**, no censored f-bombs.
- **D-04:** **Meanness ceiling** is the locked sample batch (e.g. "embarrassed for you", "not one of them good, genuinely a feat", "servers that don't deserve me"). This is the **ceiling, not the floor** — most lines sit a notch below max so the brutal ones land.
- **D-05:** Existing locked rules **preserved** (PERS-01): lowercase, ≤500 chars, **one emoji max**, accurate-first, and **dials back sarcasm for genuinely serious/emotional `/ask` questions** (a knife, not a sledgehammer).
- **D-06:** **The shipped `DEXTER_SYSTEM_PROMPT` (`personality/prompts.py`) MUST be rewritten** to embed **few-shot exemplars** plus the arrogant/outward-only rules above. Root-cause finding: the current prompt is an *adjective list with zero examples*, which is why the personality "didn't translate" — LLMs imitate examples far better than descriptions. This touches shipped Phase-2 `/ask` code and is a **deliberate, in-scope foundational change for Phase 3, not scope creep** (Phase 3 IS "the personality comes alive").
- **Locked sample lines** (seed the template pools / few-shot prompt during execution): see DISCUSSION-LOG.md "Voice samples" — they are the canonical reference for the target register.

### Roast content source
- **D-07:** **HYBRID.** Hand-written **template pools** (new `personality/roasts.py`, following the existing `personality/responses.py` + `pick_random()` pattern) are the **backbone** for high-frequency / low-stakes triggers: join, leave, reactions, idle, startup, status, seasonal. Free, instant, deterministic, testable, voice = exactly what we write.
- **D-08:** **Gemini is reserved** for the **special, low-frequency** moments where live personalization pays off: **milestones** and **repeat-song callbacks that riff on the user's actual top artist**. These run at **priority 2** on the shared 15 RPM limiter and **fall back to a template** if rate-limited (>10s wait). Never let ambient roasts touch the live API.

### Where unprompted messages post
- **D-09:** New config **`DEXTER_CHANNEL_ID`** (env var, mirrors the `ERROR_LOG_CHANNEL_ID` pattern). **Ambient posts** (voice-join/leave roasts, startup, idle-loneliness) go there if set.
- **D-10:** If `DEXTER_CHANNEL_ID` is unset, **fallback chain:** last-active music text channel (`queue._text_channel_id`) → guild **system channel** → first channel the bot can post in. Never silently dead; honors Critical Rule #9 ("don't spam every channel").
- **D-11:** Reactions attach to the triggering message (no channel choice). **Repeat-song & milestone roasts** fire *during music*, so they post to the music channel (`queue._text_channel_id`), not necessarily `DEXTER_CHANNEL_ID`.

### Roast intensity & annoyance ceiling
- **D-12:** **Keep the spec's per-feature odds/cooldowns** (join 30% / 5-min per-user, late-night 50%, repeat-song & milestones 100%, leave 30%).
- **D-13:** Add **ONE unified per-user "ambient roast" ceiling** (~1 ambient roast per 5–10 min, covering join + leave + late-night *combined*) so a user bouncing in/out isn't carpet-bombed — important now that meanness is dialed up.
- **D-14:** **"Earned" roasts bypass the ceiling and always fire:** repeat-song (3+×/day) and milestones — they're tied to a real action, not ambient noise.

### `/lyrics`
- **D-15:** **Current song only.** No query argument. Personality error if nothing's playing OR if neither source returns lyrics. Genius primary → AZLyrics fallback. Reuse the existing **button-pagination pattern (`QueuePageView`)** for long lyrics.

### `/history`
- **D-16:** **Server-wide.** Recently queued songs across the whole guild; each line shows **title / artist / who requested / when**. Reuse button pagination for older pages. Reads the existing `song_history` table (indexed by guild).

### Streak & milestone mechanics
- **D-17:** **Day boundary = single configured timezone.** New config **`STREAK_TIMEZONE`** (IANA, e.g. `America/New_York`, default a sensible zone). The whole community shares one boundary — fair, avoids UTC-midnight breakage. (`datetime('now')` is UTC; streak date math must use the configured tz, NOT raw UTC.)
- **D-18:** **Strict reset.** Consecutive calendar day → +1; same day → no-op; one fully missed day → reset to 1.
- **D-19:** **Storage:** new columns on `user_profiles`: `current_streak INTEGER`, `longest_streak INTEGER`, `last_streak_date TEXT` (date-only, in configured tz). Schema addition — additive migration.
- **D-20:** **Track `longest_streak`** so roasts can twist the knife with personal bests ("your record's 30 days — let's see you choke before then").
- **D-21:** **Milestone firing:** song-count `[100,250,500,1000]` and streak-day `[7,14,30,60,100]` both **always-fire, once per threshold**, roast on hit. Song-count fires when `total_songs_queued` crosses a threshold exactly; streak fires when `current_streak` hits a threshold exactly (no separate "already roasted" bookkeeping needed).

### Claude's Discretion
- Exact wording of all template-pool lines (written + reviewed by user during execution — this phase locks the *voice standard*, not final copy).
- Exact config values for the unified ambient ceiling, `STREAK_TIMEZONE` default, status-rotation interval, idle-silence threshold (planner sets via `config.py`, consistent with existing constants).
- `/lyrics` and `/history` page sizes and exact embed layout (match existing embed/pagination conventions).
- Implementation of Genius lookup (raw HTTP + page-scrape vs a library like `lyricsgenius`) — researcher/planner call; Genius API does not serve lyrics text directly.
- Which additional seasonal dates to add for "expanded seasonal awareness" beyond the existing 5 (Dec / Oct / Feb-14 / Jan-1 / Apr-1).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Personality / voice (most important — the "didn't translate well" fix lives here)
- `personality/prompts.py` — `DEXTER_SYSTEM_PROMPT` to be **rewritten** with few-shot exemplars + arrogant/outward-only rules (D-06). Also `MOOD_CONTEXTS`, `build_chat_prompt()`.
- `personality/responses.py` — the established static **template-pool + `pick_random()`** pattern that `personality/roasts.py` must follow (D-07).
- `personality/seasonal.py` — existing 5-date seasonal logic to expand (PERS-06).
- `dexter-architecture.md` — canonical personality samples, "Squidward-meets-Dexter-Morgan" descriptor, status-line pool examples, event-listener pseudocode (§"Event Listeners", §"Streak Tracking"), roast config constants (`UNPROMPTED_ROAST_CHANCE`, `ROAST_COOLDOWN_SECONDS`, `LATE_NIGHT_ROAST_CHANCE`, `REPEAT_SONG_ROAST_THRESHOLD`, `MILESTONE_THRESHOLDS`).
- `03-DISCUSSION-LOG.md` — **"Voice samples"** section: the locked sample roast lines per scenario (canonical register reference).

### Build spec & requirements
- `CLAUDE.md` — Unprompted Behavior, Now Playing Embed, Personality (System Prompt Core Rules, Mood, Seasonal), Critical Rules (#7 one-emoji, #8 lowercase, #9 designated-channel-only).
- `.planning/REQUIREMENTS.md` — PERS-02…09, LYRIC-01, HIST-01.
- `.planning/ROADMAP.md` §"Phase 3: Alive" — goal + 5 success criteria.

### Codebase integration
- `cogs/events.py` — current stub (only `on_message` buffer-feeding); Phase 3 adds `on_voice_state_update`, reactions, and likely the background loops or hooks.
- `cogs/music.py` — `/lyrics`, `/history` commands live here (per STRUCTURE.md); `queue._text_channel_id`; `QueuePageView` pagination to reuse.
- `services/lyrics.py` — to be created (`LyricsService`: Genius + AZLyrics).
- `database.py` — `song_history` (powers `/history`), `user_profiles` (add streak columns), `SCHEMA_SQL`.
- `bot.py` — background-task registration (status rotation, idle check) follows existing `idle_check` / `cache_cleanup` loop pattern.
- `config.py` — add `DEXTER_CHANNEL_ID`, `STREAK_TIMEZONE`, roast/streak/status constants (Phase 3 settings, currently absent).
- `.planning/codebase/{ARCHITECTURE,STRUCTURE,CONVENTIONS,INTEGRATIONS}.md` — current built state.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`personality/responses.py` + `pick_random()`** — exact pattern for the new `personality/roasts.py` template pools (D-07).
- **`QueuePageView`** (`cogs/music.py`) — button-pagination view; reuse for `/lyrics` and `/history` (D-15, D-16).
- **`queue._text_channel_id`** — already-tracked per-guild text channel for the post-channel fallback chain (D-10/D-11).
- **`ERROR_LOG_CHANNEL_ID` pattern** (`config.py:50`) — template for the new optional `DEXTER_CHANNEL_ID` (D-09).
- **`get_seasonal_context()`** (`personality/seasonal.py`) — extend for expanded seasonal awareness.
- **Background-loop pattern** in `bot.py` (`idle_check`, `cache_cleanup`) — model for status rotation + idle-loneliness loops.
- **`song_history`** table — already indexed `(guild_id, queued_at DESC)`, powers `/history` with no schema change.
- **`get_recent_songs()`** (`database.py`) — likely reusable for `/history`.

### Established Patterns
- New slash commands → method in the relevant cog; new service → `services/`, wired in `bot.py:on_ready()`, accessed via `self.bot.<svc>`.
- Static personality content lives in `personality/`; pure logic gets TDD in `tests/`, Discord/cog/`bot.py` code is structural-review + clean-boot only (per PROJECT.md testing convention).
- Gemini shared **15 RPM** limiter, priority 1 (user, wait ≤60s) vs priority 2 (background, reject if >10s) — Gemini-backed roasts use **priority 2 + template fallback**.
- SQLite `datetime('now')` (UTC) acceptable through Phase 3 — **but streak date math must convert to `STREAK_TIMEZONE`**, not use raw UTC.

### Integration Points
- `on_voice_state_update` in `cogs/events.py` (currently absent) — join/leave/move roasts + idle-timer interplay with existing music idle-leave.
- Reaction listeners extend the existing `on_message` in `cogs/events.py`.
- Streak update hooks into the per-command activity path (same place `last_active_at` / daily stats are updated).
- `services/lyrics.py` consumed by `/lyrics` in `cogs/music.py`; uses `GENIUS_TOKEN` (already an expected env var, unused today).
</code_context>

<specifics>
## Specific Ideas

- **Personality reference:** "Squidward-meets-Dexter-Morgan" — but explicitly **without** Deadpool's fourth-wall self-reference. The Deadpool influence is *attitude/irreverence/confidence*, NOT meta-commentary about being a bot.
- The **before/after dial** the user converged on, in order of corrections: (1) cut bot-self-awareness, (2) cut pop-psych, (3) cut self-deprecation, (4) crank meanness up a notch. The endpoint: **straight arrogant contempt at the user's actual data.**
- Canonical good line (the formula): `marcus. back with the drake. forty-seven plays last week. one artist, one emotion, zero growth. impressive commitment to being boring.`
- Startup must NOT be self-deprecating — replace the spec's `"did you miss me. probably not."` with an arrogant variant (e.g. `i'm back. the queue fell apart without me, obviously. let's see what damage you did.`).
- Full locked sample set per scenario is preserved in `03-DISCUSSION-LOG.md`.
</specifics>

<deferred>
## Deferred Ideas

- **Streak-broken roast** — Dexter roasts the *loss* when a streak ends ("14-day streak. gone. all that effort, wasted. anyway."). A notch beyond PERS-09's "roast on milestone hits" wording. Easy additive feature; revisit if desired. (Not built in Phase 3.)
- **Per-user timezones for streaks** — most accurate but Discord doesn't expose tz; leans toward Phase 4 scale. Single `STREAK_TIMEZONE` chosen instead.
- **One-day grace / "streak freeze"** — friendlier reset rule; rejected for strict reset in Phase 3.
- **`/lyrics` arbitrary-song query argument** — beyond LYRIC-01's "current song"; rejected to keep scope tight.
- **`/history` per-user filter** — beyond HIST-01's "for the server"; rejected.

*All other discussion stayed within phase scope.*
</deferred>

---

*Phase: 3-alive*
*Context gathered: 2026-06-11*
