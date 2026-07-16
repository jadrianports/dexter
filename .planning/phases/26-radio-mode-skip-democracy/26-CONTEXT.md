# Phase 26: Radio Mode & Skip Democracy - Context

**Gathered:** 2026-07-16
**Status:** Ready for planning

> **Session note:** The user launched `/gsd:discuss-phase 26`, was presented four phase-specific
> gray areas, **explicitly selected all four**, and **affirmatively chose the recommended option for
> every question** (D-01…D-20) — not an AFK adoption. They twice chose "More questions" to go deeper
> (radio engine, radio lifecycle) and once chose "Explore more gray areas" after the four areas
> closed, which surfaced D-18/D-19/D-20. All numeric knobs (majority ratio default, lookahead depth,
> refill batch size) remain planner's discretion per the standing Phase 11/13/14/15/16/17/21/25
> precedent.
>
> This phase spends **DJ-01** (radio/endless mode) and **DJ-02** (skip-voting/queue democracy).
> **DJ-03 (crossfade) is Phase 27's** spike-gated scope — explicitly NOT here.

<domain>
## Phase Boundary

Phase 26 delivers two **additive** changes over the existing music engine:

- **DJ-01 (radio / endless mode):** a user seeds a track or artist and Dexter keeps the queue
  flowing indefinitely off the taste brain — no manual `/play` — until stopped. Built by **reusing
  the existing `cogs/ai.py::try_auto_queue` Gemini brain with its round cap lifted** and a seed
  anchor injected (D-01/D-02), refilled on a **lookahead** trigger so Phase 6's zero-gap prefetch
  keeps working (D-10).
- **DJ-02 (skip democracy):** with more than one listener in voice, a skip requires a **strict
  majority of non-bot voice members** (ratio configurable) before the track actually skips, and
  Dexter **narrates the running tally publicly** from templated (never Gemini-generated) copy.
  A **solo listener still skips instantly** (SC-4, locked by the roadmap). The **track's requester**
  is the only bypass.

**In scope:**
- A `/radio start [seed]` + `/radio stop` subcommand group (D-06); in-memory per-guild armed state
  (D-08); disarm on `/radio stop`, `/stop`, and idle/voice-empty teardown (D-07); loop-mode mutual
  exclusion (D-11); non-destructive start over an existing queue (D-12).
- An uncapped-rounds radio refill path reusing `try_auto_queue`'s brain: seed anchor added to
  `build_recommendation_prompt` (D-02), a **session played-set** hint + **independent hard
  post-filter** against repeats (D-03), silent retry-next-cycle on a rejected priority-2 refill
  (D-04), radio tracks still `was_auto_queued=True` but with the `auto_queue_ignored` memory write
  and the "you ignored my picks" announce **suppressed while radio is armed** (D-05).
- A vote-gated skip at **ONE choke point** shared by both the `/skip` slash command and the
  now-playing `⏭ Skip` button (D-15); `/skip` itself is the vote, idempotent per user (D-14);
  votes reset on track change with the threshold recomputed live (D-17); public templated tally
  (D-16/D-18); requester-only bypass, bot-queued tracks always vote (D-13a/D-13b).
- **Two new pure `logic/` seams** — a radio refill gate and a skip-vote decision — both keyword-only
  and mock-free-testable, with cog glue dispatching on the returned value (D-19, Phase 10 D-02 rule).
- Additive global config knobs in `config.py` only (D-21).

**Out of scope (belongs to later phases / future milestone):**
- **Crossfade (DJ-03)** → **Phase 27**, spike-gated. Nothing in this phase may pre-commit the
  playback engine to a crossfade design; Phase 27 explicitly sequences *after* 26 so the spike risk
  isn't compounded with radio/skip-voting work.
- Portfolio finish (PORT-02/CICD-02/CICD-03) → Phase 28.
- **Any new table, schema column, or per-guild config** — no `guild_config` column, no `/setup`
  toggle, no `GuildConfigService` surface (D-21). Both features are user-invoked music commands,
  already governed by the Phase 20 `interaction_check` choke point.
- **Any new memory kind, memory weighting, or write-path change** — a vote-skipped track records via
  the *existing* `mark_song_skipped` and nothing more (D-20). Phase 25's SC-3 byte-identical
  guarantee stays intact; the memory subsystem is not reopened.
- Radio persistence across restart — deliberately rejected (D-08).
- An admin/owner skip bypass — deliberately rejected (D-13a); it would reinstate the exact
  unilateral power DJ-02 removes.
- The SQL co-occurrence engine as radio's source — rejected (D-01); `/discover` stays as-is.

</domain>

<decisions>
## Implementation Decisions

### Radio's engine & seed (DJ-01)

- **D-01 (user-selected): radio = the existing Gemini auto-queue brain with the round cap lifted.**
  Reuse `cogs/ai.py::try_auto_queue`'s pipeline rather than building a second recommender: it
  already carries the recent-history context, the Phase 14 recently-skipped **negative hint**, the
  unattributed **room-taste positive blend**, the priority-2 `chat()` call, the
  `validate_youtube_match` **token-set hallucination validator**, the duration/livestream guards,
  and the `should_start_playback` voice-client gate. Radio's difference from auto-queue is the
  `AUTO_QUEUE_MAX_ROUNDS = 3` cap (and its reset-on-human-`/play`), plus the seed anchor.
  **Known cost the planner must respect:** the refill is a **priority-2** call, which the limiter
  **rejects outright when the wait exceeds 10s** — see D-04.
  *(Rejected: **SQL co-occurrence only** (the `/discover` engine) — zero Gemini cost and structurally
  unable to hallucinate, but `get_artist_cooccurrence` only knows artists **this guild has already
  played together**, so a fresh/small server's radio dries up immediately; it also returns artists,
  not tracks. Rejected: **hybrid SQL-first/Gemini-fallback** — best coverage, but two engines to
  build, tune, and test, and two different quality bars inside one feature.)*

- **D-02 (user-selected): the seed ANCHORS the prompt; existing context STAYS.** The seed becomes an
  explicit anchor line **added to** the existing recent-history + room-taste prompt (one new
  optional slot on `personality/prompts.py::build_recommendation_prompt`, mirroring how
  `recently_skipped` / `positive_taste` were added in Phase 14 — optional, omitted when unset, so
  the auto-queue path stays byte-identical). Dex starts near the seed and drifts naturally as the
  session's own history accumulates, which is how real radio behaves.
  *(Rejected: **seed replaces the history context** ("pure artist radio") — higher fidelity and never
  drifts, but throws away the taste brain this milestone is built on and gets repetitive fast.
  Rejected: **seed + an explicit drift-control knob** — a tuning surface with no obvious right value
  and no way to feel it out while live-Discord UAT is parked behind the host.)*

- **D-03 (user-selected): repeat avoidance = a session played-set hint + an INDEPENDENT hard
  post-filter.** Radio runs indefinitely but `try_auto_queue` only shows Gemini the last ~10 songs,
  so a long session recycles. Track the `video_id`s radio has queued **this session**, feed them to
  the prompt as an "already played" hint, **and independently reject any duplicate after YouTube
  resolution**. This mirrors the **Phase 14 D-02 pattern exactly** — a prompt hint *plus* an
  independent hard gate, because Gemini's compliance is never the guarantee (the same reasoning that
  produced `is_recently_skipped_artist` as a second gate behind `validate_youtube_match`).
  *(Rejected: **prompt hint only** — trusts the model as the sole guard, the exact thing the
  hallucination validator exists because Gemini doesn't reliably do. Rejected: **rely on the existing
  recent-10 history** — zero code, but a long session visibly cycles, undermining DJ-01's promise.)*

- **D-04 (user-selected): a rejected/empty refill is SILENT — log and retry next cycle.** Radio stays
  armed; the next track-end tries again. Matches how `try_auto_queue` already handles an empty Gemini
  response (`log.info` + `return`), and keeps radio from spamming the channel with quota excuses.
  **Accepted risk:** if the queue is fully drained when a refill fails, the room goes quiet with no
  explanation — mitigated in practice by the D-10 lookahead (refills start while tracks remain, so a
  single failure has runway to retry before dead air).
  *(Rejected: **narrate each failed refill** — honest and in-character, but on a busy budget it fires
  repeatedly and exposes internal quota mechanics to a room that didn't ask. Rejected: **escalate
  radio to priority 1** — radio always works, at the cost of starving `/ask` and roasts, which is
  exactly the shared-15-RPM tension the priority tiers exist to manage.)*

- **D-05 (user-selected): radio tracks stay `was_auto_queued=True`, but the ignored-signal is
  SUPPRESSED while radio is armed.** Keeping the flag preserves `/skips` analytics, `song_history`'s
  `was_auto_queued` column, and `mark_song_skipped` accuracy. But during a long radio session people
  skip constantly, and the existing `auto_queue_results["skipped"]` → `AUTO_QUEUE_IGNORED` announce +
  the `auto_queue_ignored` **memory write** would fire repeatedly: skipping during radio is normal
  channel-surfing, **not a verdict on Dex's taste**, and memorializing it would poison the taste brain
  with noise. So while radio is armed, gate off the ignored-signal announce and its memory write.
  *(Rejected: **everything fires as-is** — zero new branches, but an hour of radio writes a stream of
  `auto_queue_ignored` memories and repeatedly nags the room: a behavior regression in a feature
  meant to run unattended. Rejected: **don't mark radio tracks auto-queued at all** — no nagging, but
  silently breaks `/skips` analytics and hides radio's contribution from `song_history`.)*

- **D-06a (user-selected): ONE free-text seed string; Gemini interprets track-vs-artist.** A single
  **optional** seed arg goes into the D-02 anchor slot as-is — Gemini already handles "sounds like X"
  whether X is an artist or a song. **When omitted:** seed from the currently-playing track, falling
  back to the room's recent history when nothing is playing. No parsing, no new resolution code — and
  because the seed only steers the *prompt*, a misread costs nothing: the hallucination validator
  still gates every actual track that gets queued.
  *(Rejected: **explicit track-vs-artist choice** — unambiguous, but a clunkier command surface for a
  value that only ever becomes one line of prompt text. Rejected: **resolve the seed through YouTube
  first** — grounds the seed in something real, but spends a search on every radio start and forces a
  track interpretation onto what may have been an artist request.)*

### Radio's control & lifecycle (DJ-01, SC-1/SC-2)

- **D-06b (user-selected): `/radio start [seed]` + `/radio stop` — a subcommand group.** Matches the
  dominant pattern in the codebase (`/playlist`, `/jam`, `/memory`, `/setup`, `/guilds`).
  **Critically, it sidesteps the trap in a single `/radio [seed]` command**, where a seed value of
  "off"/"stop" is indistinguishable from an artist actually named that.
  *(Rejected: **`/radio [seed]` with an on|off choice arg** (the `/autolyrics` / `/filter` shape) —
  fewer keystrokes, but seed and on/off are two different kinds of argument crammed into one command.
  Rejected: **a flag on `/play`** — ties the seed to a real resolved track for free, but buries the
  phase's headline feature inside an existing command and gives it no natural "off".)*

- **D-07 (user-selected): `/stop` and the idle/voice-empty teardown BOTH disarm radio; a human
  `/play` mid-radio only INJECTS.** `/stop` must disarm — otherwise it clears the queue and radio
  instantly refills it, producing an **unstoppable bot** and the clearest possible **SC-2 violation**
  ("no leftover auto-refill behavior"). The idle-leave path disarms for the same reason. But a human
  `/play` mid-radio just adds their track and radio keeps going — **asking for a song is not the same
  as ending the station**. (Note this deliberately *differs* from `/play`'s existing
  `reset_auto_queue()` behavior; the planner must not conflate the two.)
  *(Rejected: **any human `/play` also disarms** — mirrors today's `auto_queue_rounds` reset and is
  consistent, but makes radio fragile: one person adding one song silently kills a mode nobody asked
  to end. Rejected: **only `/radio stop` ever disarms** — predictable, but `/stop` becomes a lie and
  that IS the leftover-refill failure SC-2 exists to prevent.)*

- **D-08 (user-selected): radio state is IN-MEMORY and dies on restart.** It lives on the per-guild
  runtime object (`MusicQueue` / `ServerState` — planner's call, see Discretion), **not** persisted
  to `guild_queues` JSONB, **no schema change**. A restart drops the room back to manual queueing,
  which is **honest given the on-demand hosting model: the bot going down IS the session ending.**
  Zero risk of a restored ghost radio autonomously refilling a queue nobody's listening to.
  `queue.auto_lyrics` is the precedent for in-memory per-guild state.
  *(Rejected: **persist in `guild_queues` JSONB + restore** — nicer continuity, but a crashed bot
  could come back up and start autonomously queueing into a room, and it adds radio to the payload
  carried by the scar-heavy restore path (index clamp CR-03, rejoin gate). Rejected: **in-memory but
  explicitly disarmed at every teardown site** — arguably just the *implementation* of this decision
  rather than a different choice; the planner should honor its spirit (explicit disarm at teardown,
  per D-07) rather than relying on object lifetime.)*

- **D-10 (user-selected): refill on a LOOKAHEAD trigger — while tracks still remain — not on empty.**
  Refill when the queue drops to N tracks remaining (N = planner's discretion), checked at the
  existing `_on_track_end` choke point. **There is always a next track, so Phase 6's prefetch keeps
  doing its job and radio is genuinely gapless.** On-empty refill would stall on a Gemini call *plus*
  a YouTube resolve at every track boundary — audible dead air that makes radio feel broken, not
  endless, and it would undo exactly what Phase 6 spent a whole phase eliminating.
  *(Rejected: **on-empty — reuse `TrackEndAction.AUTOQUEUE` unchanged** — least new code and no new
  trigger to make generation-safe, but every refill is a hole in the audio. Rejected: **a time-based
  background refill loop** — decouples refill from playback, but adds a background loop racing the
  playback engine and the generation counter for no benefit the lookahead check doesn't give.)*

- **D-11 (user-selected): radio and loop mode are MUTUALLY EXCLUSIVE, and each says so.**
  `/radio start` turns loop off; `/loop` disarms radio; both announce it in their response. The two
  genuinely contradict: `LoopMode.QUEUE` means the queue never exhausts (so with D-10's lookahead,
  radio would pile tracks onto a looping queue forever), and `LoopMode.SINGLE` means the same track
  repeats and radio never advances. Note `MusicQueue.clear()` already resets `loop_mode` to `OFF`, so
  this largely formalizes what teardown does.
  *(Rejected: **radio wins silently** — fewer moving parts, but `/loop` and the now-playing embed's
  Loop field would keep reporting a mode that isn't in effect: a lie in the UI. Rejected: **let them
  coexist** — least code, but the emergent behavior is genuinely bad and would surface as a bug
  report, not a feature.)*

- **D-12 (user-selected): `/radio start` over an existing queue KEEPS the queue — radio takes over at
  the end.** Existing tracks play out untouched; radio starts refilling behind them once the queue
  drops to the D-10 lookahead threshold. Non-destructive: nobody loses queued songs to a command they
  may not have realized was disruptive, and it reuses the same refill path with no special "starting"
  case.
  *(Rejected: **clear the queue and start fresh** — gives an instant obvious response, but destroys
  other people's queued tracks, **which is precisely the unilateral-queue-hijacking problem DJ-02 is
  fixing in this same phase**. Rejected: **refuse until the queue is empty** — safest and unambiguous,
  but makes the phase's headline feature annoying to start for a conflict that has a good
  non-destructive answer.)*

### Skip vote threshold (DJ-02, SC-3/SC-4)

- **D-09 (user-selected): MAJORITY OF LISTENERS, computed live; the ratio is a config knob.** The
  requirement is derived from the non-bot members currently in voice, with the fraction as a
  `config.py` knob (default = half; exact default is planner's discretion). Scales with the room and
  satisfies **both** readings of the roadmap criterion ("a configurable vote threshold (or listener
  majority)") at once. A fixed count cannot: **2 votes is unanimity in a duo and trivial in a party
  of twelve.**
  *(Rejected: **a fixed configurable count** (`SKIP_VOTES_REQUIRED`) — dead simple and trivially
  testable, but wrong at both ends of the room-size range, and the whole point of DJ-02 is that a
  small clique shouldn't hijack a big room. Rejected: **majority with an upper cap** — handles the
  pathological 20-person channel, but at Dexter's actual scale that room doesn't exist, so it's a
  knob defending a hypothetical.)*

- **D-09b (user-selected): listeners = EVERY non-bot member in the voice channel.** Reuse the exact
  enumeration `_on_track_end` and the auto-queue taste blend already use
  (`[m for m in voice_client.channel.members if not m.bot]`). **One definition of "who's in the room"
  across the whole codebase**, no new edge cases — and someone self-muted is still listening, so
  excluding them would be wrong anyway.
  *(Rejected: **exclude self-deafened members** — more correct in principle (a deafened member can't
  hear the track, so counting them inflates the threshold), but it forks the listener definition away
  from every other place in the code for a rare case. Rejected: **exclude deafened + AFK-channel
  members** — most accurate tally, most new state to read, test, and keep in sync mid-vote.)*

- **D-09c (user-selected): STRICT MAJORITY — strictly more than half.** 2 listeners need 2, 3 need 2,
  4 need 3. **One of two people is not a majority**, so a duo must agree — the honest reading of the
  word, and it keeps the gate meaningful at the small room sizes Dexter actually runs in.
  **Accepted tradeoff:** in a duo, one holdout blocks every skip — mitigated by the D-13a requester
  bypass.
  *(Rejected: **round down** (2→1, 3→2, 4→2) — skips stay easy and no single holdout blocks, but a duo
  gets zero democracy, and two-person voice channels are the common case for a bot this size, so the
  feature would mostly not exist. Rejected: **strict majority with a hardcoded 2-listener exception**
  — optimizes each room size for feel, at the cost of an exception in a rule that's otherwise one
  clean line of arithmetic.)*

- **D-13a (user-selected): the TRACK'S REQUESTER is the ONLY bypass.** Whoever queued the track can
  pull their own pick without a vote — `Track.requested_by` is already on the model, so it's free.
  **Retracting your own song is not a hijack**, and it's the escape hatch from D-09c's duo-holdout
  case. **Nobody else bypasses** — an admin/owner override would quietly reinstate exactly the
  unilateral power DJ-02 removes. *(SC-4's solo-listener instant skip is locked by the roadmap and
  independent of this rule.)*
  *(Rejected: **requester + `manage_guild` admins** — practical for moderation, but then the loudest
  admin still owns the queue and "one user can't unilaterally hijack" becomes "one privileged user
  can". Rejected: **nobody bypasses, pure democracy** — ideologically clean and least code, but you
  can't withdraw your own misclick and a duo holdout locks the queue with no recourse.)*

- **D-13b (user-selected): bot-queued tracks (radio + auto-queue) ALWAYS go to a vote.** Radio and
  auto-queue tracks carry `requested_by = self.bot.user.id`, so **no human owns them and D-13a falls
  through naturally with zero special-casing.** Nobody chose the track, so nobody gets to retract it —
  and Dex's own picks are exactly the ones a room should get a collective say on.
  *(Rejected: **bot-queued tracks skip instantly** — keeps radio feeling responsive rather than
  committee-run, but it means that during radio (the phase's *other* headline feature) skip democracy
  effectively switches off, undercutting DJ-02 in the exact session where the queue is most shared.)*

### Vote mechanics & narration (DJ-02, SC-3)

- **D-14 (user-selected): `/skip` IS the vote — idempotent per user.** Each `/skip` from a distinct
  user registers one vote; a repeat `/skip` from the same user does not stack. No new UI, no message
  lifetime to manage — and it's what people already type. The existing
  `SKIP_COOLDOWN_SECONDS = 2` cooldown stays as the anti-spam guard.
  *(Rejected: **first `/skip` posts a vote message with a button** — visually obvious and easy to
  join, but adds a view whose lifetime must be torn down on track change, and the codebase's
  persistent-view rules (`timeout=None` + stable `custom_id` registered in `setup_hook`) are aimed at
  **durable** controls, not ephemeral per-track polls. Rejected: **reaction voting on the now-playing
  embed** — lightweight-feeling, but reaction handling is a separate event path with its own races
  and it collides with the now-playing message that is deleted and re-sent on every track change.)*

- **D-15 (user-selected): BOTH skip routes go through ONE vote choke point.** The `/skip` slash
  command (`cogs/music.py:1663`) and the now-playing `⏭ Skip` button (`:377` → `_do_skip`) both call
  the same vote-gated path; **a button press is a vote exactly like `/skip`.** Directly follows the
  **Phase 20 OWNER-05 precedent** ("enforced at ONE choke point, never per-cog checks"). The
  alternative leaves a one-click bypass sitting on a persistent message, which makes the gate
  decorative rather than real.
  *(Rejected: **button skips instantly, only `/skip` votes** — zero risk to the persistent view and
  the button keeps its snappy feel, but DJ-02 is then trivially defeated by clicking instead of
  typing: not a feature, a hole. Rejected: **remove the button when multiple listeners are present**
  — unambiguous, but mutating the persistent view's children from live voice state is more moving
  parts than routing one call through the shared gate.)*

- **D-16 (user-selected): the tally is PUBLIC, in Dex's voice.** Each vote posts a visible line
  ("2 of 3. one more and this track's gone."). **A vote nobody can see isn't democracy** — the room
  needs to know a vote is open in order to join it — and it's the personality moment SC-3 asks for
  ("Dexter narrates the running tally in response to each vote"). Naturally bounded: at most one line
  per listener per track.
  *(Rejected: **ephemeral confirmation to the voter, public only on success** — zero channel noise,
  but nobody else knows a vote is open so the second vote never comes and the feature quietly fails.
  Rejected: **edit one tally message in place** — cleanest channel, but another per-track message
  lifetime to manage and it collides with the now-playing message's delete-and-resend cycle.)*

- **D-17 (user-selected): votes reset on TRACK CHANGE; the threshold is RECOMPUTED LIVE at each
  vote.** Votes are scoped to the current track and cleared whenever it changes. The requirement is
  derived from who is in voice **at the moment of each vote**, not frozen when the vote opened.
  **No timeout knob — the track ending IS the timeout.** A departed voter's vote **stays counted**,
  so a walkout can't strand an open vote below a threshold that just dropped.
  *(Rejected: **track change + a vote timeout** — stops a stale half-vote riding a 10-minute track,
  but it's another knob with no obviously right value and no live UAT to feel it out, and the track
  boundary already bounds the vote's life. Rejected: **drop a voter's vote when they leave voice** —
  most principled (the tally only reflects people present), but needs `on_voice_state_update` wired
  into vote state and can decrement a tally mid-vote in a way the room finds confusing.)*

- **D-18 (user-selected): tally text is TEMPLATED, with numbers interpolated by CODE.** Add a
  response pool to `personality/responses.py` with counts formatted in by code — the same pattern as
  `AUTO_QUEUE_ANNOUNCE` / `DISCOVER_NO_HISTORY` / `VISION_ROAST_FALLBACKS`. **Honors Critical Rule 12
  structurally** (hard numbers come from live state, never a model), costs nothing against the shared
  15 RPM budget, and **works when Gemini is rate-limited — a skip vote fires several times per track
  and cannot depend on the AI being available.**
  *(Rejected: **Gemini-generated with the tally passed in** — freshest personality, but spends a chat
  call per vote on the shared budget, needs a template fallback anyway when the limiter says no, and
  hands the model numbers it could restate wrong. Rejected: **templated tally + a Gemini flourish on
  the final skip** — caps cost at one call per skip, but is two narration paths to build and test for
  a line most people barely read.)*

### Cross-cutting (surfaced when the user chose "Explore more gray areas")

- **D-19 (user-selected): BOTH features get a pure `logic/` seam.** A **radio refill gate** (armed?
  below the lookahead threshold? filter the already-played set) and a **skip-vote decision**
  (threshold arithmetic, requester bypass, solo case, tally state) each become pure, keyword-only,
  mock-free-testable functions, with cog glue **dispatching on the returned value and never mirroring
  the branch logic back** (the Phase 10 D-02 rule). Both hold real branching logic that is otherwise
  trapped behind Discord objects, and **the vote rule especially is exactly the arithmetic that needs
  mock-free tests to lock SC-3/SC-4.** Follows `logic/playback.py` / `logic/vision.py` /
  `logic/proactive.py` convention (module names + exact signatures are planner's discretion).
  *(Rejected: **skip-vote seam only** — radio's gate looks like a thin config check, but it isn't once
  armed-state + lookahead depth + the played-set filter combine, and that IS the SC-1/SC-2 logic.
  Rejected: **let the planner decide per feature** — five phases of precedent say the decision logic
  gets extracted; leaving it open invites the one answer the convention already rules out.)*

- **D-20 (user-selected): a vote-skipped track records via the EXISTING `mark_song_skipped` and
  NOTHING more.** It flows into the Phase 14 recently-skipped negative hint like any other skip. **No
  new memory kind, no new weighting.** A room voting a track down is genuinely strong taste signal
  and the existing plumbing already carries it. (The `auto_queue_ignored` memory write stays
  suppressed during radio per D-05 — that's the only interaction.)
  *(Rejected: **weight a voted skip higher than a solo skip** — intellectually appealing (collective
  rejection means more than one person's whim), but introduces a new weighting concept into a
  subsystem that **just came through Phase 25's SC-3 byte-identical gate**, for a signal already
  captured. Rejected: **don't record vote-skips at all** — keeps the taste brain clean, but
  suppressing `mark_song_skipped` also breaks `/skips` analytics and skip history that predate this
  phase.)*

- **D-21 (user-selected): NO new per-guild config — global `config.py` knobs only.** No
  `guild_config` column, no `/setup` toggle, no `GuildConfigService`/`AmbientSurface` surface.
  **Both features are user-invoked music commands, not unprompted ambient surfaces** — the
  `AmbientSurface` machinery exists to gate what Dexter does **unprompted at strangers**, which
  neither of these is. They are already governed by the Phase 20 `interaction_check` choke point
  (block/silence). Config stays global like every other music knob.
  *(Rejected: **`/setup` toggles for radio and skip-voting** — consistent with v1.4's per-guild
  philosophy, but adds schema columns and a cache surface for features carrying none of the abuse
  risk that motivated per-guild gating. Rejected: **a per-guild skip-vote ratio** — the one knob where
  server culture genuinely varies, but it's a schema change plus a cache path for a number that has a
  sane default, with no live UAT to prove servers want it different.)*

### Claude's / Planner's Discretion (do NOT re-ask the user)

Per the standing Phase 11/13/14/15/16/17/21/25 "discretion-on-numbers" precedent:

- **Every numeric knob:** the D-09 majority **ratio default** (half), the D-10 **lookahead depth**
  (how many tracks remaining triggers a refill), the **tracks-per-refill batch size** (reuse
  `AUTO_QUEUE_SONGS_PER_ROUND = 3` or a radio-specific knob), and any radio session-set cap.
  All new knobs go in `config.py` as global settings (D-21).
- **Where radio's armed state lives** — `MusicQueue` (alongside `auto_lyrics`, which survives
  `clear()` as a server preference) vs. `ServerState` (alongside `auto_queue_rounds`, the
  auto-queue-adjacent runtime state). Strong steer: whichever makes the D-07 disarm sites
  (`/stop`, idle-leave) and the D-11 loop interaction cleanest. **Must NOT be persisted** (D-08).
- **How the round cap is lifted for radio** — a radio-aware branch inside `try_auto_queue`, an
  explicit `unlimited`/`is_radio` keyword-only param, or a thin radio wrapper calling into a shared
  refill core. Strong steer: **the auto-queue path must stay byte-identical when radio is disarmed**
  (the standing additive-change discipline; mirrors Phase 16's `pre_recalled_memories` default-None
  bypass and Phase 14's optional-`kind`-clause pattern).
- **The exact `logic/` module names + signatures** for the two D-19 seams (e.g.
  `logic/radio.py::should_refill_radio`, `logic/skip_vote.py::decide_skip`) — follow
  `logic/playback.py` / `logic/vision.py` / `logic/proactive.py` convention: keyword-only,
  clock/RNG-injected, no Discord imports.
- **The exact shape of the D-15 shared choke point** — whether `_do_skip` becomes the gate, a new
  shared `_try_skip` wraps both callers, or the vote check sits in front of both. Requirement: **one
  gate, both routes** (never a per-surface check).
- **Where the D-03 session played-set lives** and how it's bounded (it grows for the session's life —
  cap it or scope it to the armed-radio lifetime; it dies with radio per D-08).
- **How the D-05 ignored-signal suppression is expressed** — an `if radio_armed` guard around the
  existing announce + memory write, vs. threading a flag. Keep it a minimal, obviously-reviewable
  gate; the auto-queue path must be byte-identical when radio is off.
- **Whether the D-02 seed anchor is a new optional param on `build_recommendation_prompt`** (the
  Phase 14 `recently_skipped`/`positive_taste` precedent — strongly preferred) or a separate prompt
  builder.
- **Exact test shape.** Mock-free unit tests for both D-19 pure seams (this is where SC-1/SC-2/SC-3/
  SC-4 get locked — especially the D-09c strict-majority arithmetic at 1/2/3/4 listeners, the D-13a
  requester bypass, and the SC-4 solo-instant-skip case). Per `TESTING.md`, the Discord/process glue
  stays untested-by-design (structural review + clean boot). Add a regression guard that the
  auto-queue path is unchanged when radio is disarmed.
- **Wording of all new personality copy** (D-18 tally pool, radio start/stop/disarm lines, the D-11
  mutual-exclusion notices) — lowercase, ≤1 emoji, accurate-first (CLAUDE.md Critical Rules 7/8).

### Reviewed Todos
None — `todo.match-phase 26` returned zero matches.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements (this phase)
- `.planning/ROADMAP.md` §"Phase 26: Radio Mode & Skip Democracy" — goal + the 4 success criteria
  (SC-1 seeded endless refill, SC-2 stop leaves no auto-refill, SC-3 vote threshold + narrated tally,
  SC-4 solo skip unregressed). Also §"Phase 27: Crossfade Playback (Spike-Gated)" — **read to confirm
  what this phase must NOT pre-commit**; Phase 27 depends on 26 precisely to contain spike risk.
- `.planning/REQUIREMENTS.md` §"New Music Muscle" — **DJ-01** and **DJ-02** verbatim; **DJ-03 is
  Phase 27's**, and §"Future Requirements → Music" (DJ-F1 synced lyrics, DJ-F2 crossfade-if-descoped)
  — neither is this phase. Also §"Out of Scope".
- `.planning/PROJECT.md` §"Current Milestone: v1.5" — the "New music muscle" framing + the standing
  **Descope Rule**; §"Key Decisions" — the rate-budget + accuracy-firewall invariants this phase
  inherits. The phase-close step adds the shipped radio/vote decisions here.

### The playback engine — READ BEFORE TOUCHING (the scar surface)
- `cogs/music.py::_on_track_end` (`:842`) — the natural-advance choke point; **D-10's lookahead
  refill trigger lands here**. Note it dispatches on `decide_on_track_end`'s returned
  `TrackEndAction` and must keep doing so (Phase 10 D-02).
- `cogs/music.py::skip` slash command (`:1661`–`:1695`) and `cogs/music.py::_do_skip` (`:1006`) —
  **the two skip entry points D-15 unifies behind one gate.** Both call `mark_song_skipped` +
  `auto_queue_results["skipped"] += 1` for auto-queued tracks (D-20 keeps this), `queue.skip()`,
  `_persist_queue`, `make_task(self._play_track(...), name="play-after-skip")`, and
  `_refresh_now_playing`.
- `cogs/music.py::NowPlayingView.skip_button` (`:376`–`:391`) — the persistent-view `⏭ Skip` button
  (`custom_id="dex:np:skip"`) that currently calls `_do_skip` directly; **the D-15 bypass hole**.
- `cogs/music.py::_play_track` (`:628`) + the generation counter (`:685`–`:687`, `:751`, `:784`) —
  the double-play guard. **Do not add a `voice_client.stop()` before `_play_track`** (CLAUDE.md
  Phase 1 gotcha). Radio refill must not race teardown.
- `cogs/music.py::_prefetch_next_track` (`:742`) — the generation-guarded zero-gap prefetch **D-10
  exists to keep working** (it needs a next track to already exist).
- `models/queue.py::MusicQueue` — `add()` (`:91`, 500 cap → `QueueFullError`), `skip()` (`:107`,
  ignores SINGLE loop), `advance()` (`:114`), `clear()` (`:213`, **resets `loop_mode` to OFF and
  monotonically advances `_play_generation` — never rewinds**), `upcoming()` (`:235`, the natural
  lookahead read), `auto_lyrics` (`:80`, **the in-memory-server-preference precedent for D-08**;
  deliberately NOT reset by `clear()`), `Track.requested_by` (`:33`, **the D-13a bypass key**),
  `Track.was_auto_queued` (`:34`, **the D-05 flag**).
- `logic/playback.py` — the pure seam (`TrackEndAction`, `decide_on_track_end`,
  `should_start_playback`, `clamp_restore_index`, `should_smart_rejoin`, `exceeds_queue_cap`). **The
  convention D-19's two new seams follow**; read its module docstring for the scar list (scar #1
  finished-song replay, scar #2 silent auto-queue, scar #4 restore index clamp). Locked by
  `tests/test_playback_logic.py`.
- `models/server_state.py::ServerState` — `auto_queue_rounds`, `auto_queue_results`,
  `reset_auto_queue()` (`:21`, called on human `/play`); `get_server_state` create-on-access
  (`:27`). **The D-08 alternative home for radio's armed state.**

### Radio's engine — the auto-queue brain being reused (DJ-01)
- `cogs/ai.py::try_auto_queue` (`:273`–`~505`) — **the D-01 engine, read end to end.** The round cap
  (`:283`, `AUTO_QUEUE_MAX_ROUNDS`) is what radio lifts; `get_recent_songs` limit 10 (`:295`) is why
  D-03 needs a session played-set; the Phase 14 recently-skipped negative hint (`:317`–`:328`), the
  room-taste positive blend (`:334`–`:357`, `guild_scoped=True`, `kind="taste_episode"`), the
  priority-2 `chat()` (`:364`) **and its silent bail on empty (`:366`–`:372`) — the D-04 precedent**,
  `validate_youtube_match` (`:405`), the D-02 independent `is_recently_skipped_artist` post-filter
  (`:425`) — **the pattern D-03's hard post-filter mirrors** — the `requested_by=self.bot.user.id` +
  `was_auto_queued=True` construction (`:449`–`:451`, **the D-13b + D-05 keys**), the
  `should_start_playback` gate + `current_index` fix (`:474`–`:485`, WR-01), and the
  `ignored_signal` announce + `auto_queue_ignored` memory write (`:487`–`:505`) — **exactly what D-05
  suppresses while radio is armed.**
- `personality/prompts.py::build_recommendation_prompt` (`:181`) + `MUSIC_RECOMMENDATION_PROMPT`
  (`:105`) — **the D-02 seed-anchor slot.** Note how `recently_skipped` (`:208`) and `positive_taste`
  (`:213`) were added as **optional params, omitted from the prompt when unset** — the precedent the
  seed anchor follows so the auto-queue path stays byte-identical.
- `logic/autoqueue.py` — `validate_youtube_match` (token-set containment, not difflib — D-12) +
  `is_recently_skipped_artist`. The hallucination guard radio inherits unchanged.
- `logic/taste.py::select_positive_taste_context` (`:151`) — the unattributed room-taste blend
  (**note the cap-checked-BEFORE-append scar**, `:178`); `resolve_decay_days` (`:186`).
- `services/gemini.py::chat` — the **priority-2 rejection-when-wait>10s** behavior underpinning D-04;
  per-guild usage tagging (Phase 20 RATE-01) — radio refills must pass `guild_id=str(guild.id)`.
- `database.py::get_recent_songs` / `get_recently_skipped` / `mark_song_skipped` — the history
  reads/writes radio and D-20 reuse unchanged.

### Config (additive global entries only — D-21)
- `config.py:53`–`54` — `AUTO_QUEUE_MAX_ROUNDS = 3` (**what radio lifts**),
  `AUTO_QUEUE_SONGS_PER_ROUND = 3` (the refill batch precedent).
- `config.py:145` — `AUTO_QUEUE_SEARCH_CANDIDATES = 3`; `config.py:234`–`236` —
  `AUTO_QUEUE_SKIP_LOOKBACK_DAYS`, `AUTO_QUEUE_SKIP_HINT_CAP`, `AUTO_QUEUE_POSITIVE_TASTE_CAP`
  (the Phase 14 knob-naming precedent for the new radio/vote knobs).
- `SKIP_COOLDOWN_SECONDS = 2` — **the D-14 anti-spam guard, unchanged**;
  `MAX_QUEUE_SIZE_PER_GUILD = 500` — the `QueueFullError` cap radio must respect (a refill into a
  near-full queue must not crash).
- `personality/responses.py` — `AUTO_QUEUE_ANNOUNCE` (`:21`), `AUTO_QUEUE_CAP_REACHED` (`:28`),
  `AUTO_QUEUE_IGNORED` (`:34`), `DISCOVER_NO_HISTORY` (`:195`) — **the D-18 templated-pool +
  `pick_random` pattern the tally copy follows.**

### CLAUDE.md invariants this phase must honor
- §"Critical Rules" **1** (all AI features share the 15 RPM limiter — radio refills are priority-2,
  D-04), **3** (kill FFmpeg explicitly — the skip path), **5/12** (**accuracy firewall: hard numbers
  from live state, never a model — the D-18 tally reason**), **7/8** (≤1 emoji, lowercase),
  **9** (designated channel only), **19** (**block/silence enforced at ONE choke point, never
  per-cog — the D-15 precedent**).
- §"Implementation Gotchas → Phase 1" — never `voice_client.stop()` before `_play_track`; the 3s
  interaction-response rule (defer or respond, then `create_task`).
- §"Implementation Gotchas → Phases 6–8" — **gate playback-start on `voice_client.is_playing()`,
  never `queue.is_playing`** (scar #2, silent auto-queue); the generation counter's role.
- §"Implementation Gotchas → Phases 9–12" — `logic/` is the pure seam and **glue dispatches on the
  returned enum/verdict, never mirrors the branch logic** (D-02 — the D-19 rule); `make_task` is for
  genuine fire-and-forget only (**`_play_track` create_task calls stay bare** — Pitfall 4).
- §"Background Tasks" + §"Music Pipeline → Playback Engine Patterns" — generation counter, channel
  tracking, silent skip, async responses.

### Prior-phase context (conventions inherited)
- `.planning/phases/14-smarter-music-brain/14-CONTEXT.md` — **the closest analog**: the
  optional-param prompt-slot pattern (D-02), the **prompt-hint + independent-hard-post-filter
  discipline (D-02/D-03)**, the taste-blend design, and the read-only-over-taste framing.
- `.planning/phases/25-smarter-memory/25-CONTEXT.md` — the immediately-prior phase; **its SC-3
  byte-identical guarantee is why D-20 refuses to touch memory weighting.**
- `.planning/phases/10-critical-path-test-coverage/*` — the `logic/` extraction convention + the
  named scar regressions D-19's seams follow.
- `.planning/phases/20-owner-control-plane*/20-CONTEXT.md` — **the OWNER-05 one-choke-point rule
  D-15 applies to skip**; also why D-21 needs no new per-guild surface (`interaction_check` already
  governs both commands).

### Testing + CI
- `.planning/codebase/TESTING.md` — "pure logic gets mock-free TDD; Discord/process glue is
  untested-by-design (structural review + clean boot)." Governs the D-19 seams' test shape.
- `tests/test_playback_logic.py` — the mock-free pattern + scar regressions the new seams' tests
  mirror.
- `tests/test_autoqueue*.py` / any test over `try_auto_queue` — **the regression surface**: the
  auto-queue path must stay byte-identical when radio is disarmed.
- `.github/workflows/ci.yml` — the blocking Ruff + pytest gate (pgvector service container).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`cogs/ai.py::try_auto_queue`** — ~90% of a radio engine already: history context, negative skip
  hint, room-taste blend, priority-2 Gemini call, hallucination validation, duration guards,
  `should_start_playback`. D-01 lifts its round cap and injects a seed.
- **`personality/prompts.py::build_recommendation_prompt`** — already takes two optional,
  omitted-when-unset context slots (`recently_skipped`, `positive_taste`); the seed anchor is a third
  (D-02).
- **`logic/autoqueue.py`** (`validate_youtube_match` + `is_recently_skipped_artist`) — radio inherits
  the hallucination guard **and** the "independent second gate" pattern D-03's repeat filter copies.
- **`Track.requested_by`** — already on the model; D-13a's bypass costs nothing, and D-13b
  (bot-queued tracks always vote) falls out for free since radio/auto-queue set it to `bot.user.id`.
- **`queue.upcoming()`** — the natural read for D-10's lookahead depth check.
- **`queue.auto_lyrics`** — the precedent for in-memory per-guild state that isn't persisted (D-08).
- **`personality/responses.py` pools + `pick_random`** — the D-18 templated-tally pattern.
- **`logic/playback.py`** — the pure-seam convention + `TrackEndAction` dispatch pattern for D-19.

### Established Patterns
- **Prompt hint + INDEPENDENT hard gate** (Phase 14 D-02): never trust Gemini's compliance as the
  only guard — D-03's repeat filter follows this exactly.
- **Optional param, omitted clause, byte-identical when unset** (Phase 14 `kind`, Phase 16
  `pre_recalled_memories`, Phase 21 `guild_scoped`): the discipline for the seed anchor **and** the
  radio branch inside `try_auto_queue`.
- **ONE choke point, never per-surface checks** (Phase 20 OWNER-05): D-15's unified skip gate.
- **`logic/` is the pure seam; glue dispatches on the returned value** (Phase 10 D-02): D-19.
- **Accuracy firewall — numbers from live state, never a model** (Critical Rule 12): D-18.
- **Voice-client state is the only ground truth for "audio is flowing"** (scar #2): any radio
  playback-start must go through `should_start_playback`, never `queue.is_playing`.
- **The generation counter guards every teardown**: refill and vote-skip must not race it.

### Integration Points
- `cogs/music.py::_on_track_end` — D-10's lookahead refill trigger (dispatching on the existing
  `TrackEndAction`).
- `cogs/music.py::skip` + `NowPlayingView.skip_button` → `_do_skip` — the two routes D-15 unifies.
- `cogs/ai.py::try_auto_queue` — the radio branch (cap lift + seed) and the D-05 ignored-signal
  suppression.
- `personality/prompts.py::build_recommendation_prompt` — the D-02 seed slot.
- `personality/responses.py` — new D-18 tally pool + radio start/stop/disarm copy.
- `config.py` — new global knobs only (majority ratio, lookahead depth, refill size) — D-21.
- New: `cogs/music.py` (or a new cog) `/radio start|stop` group; two new `logic/` modules (D-19).
- **Regression surface:** every test over `try_auto_queue`, `_on_track_end`, `_do_skip`, and
  `logic/playback.py` — plus new mock-free tests locking SC-1/SC-2/SC-3/SC-4.

</code_context>

<specifics>
## Specific Ideas

- **"Radio is auto-queue that doesn't give up."** The whole feature is the existing brain with the
  3-round cap lifted and a seed anchor — not a second recommender. Every quality property radio has
  (no hallucinated tracks, taste-aware, skip-aware) it inherits by *not* forking that path.
- **Skipping during radio is channel-surfing, not a verdict.** That's the single insight behind D-05:
  the ignored-signal exists to notice that Dex's *occasional* picks were rejected. During an hour of
  radio it would fire constantly and poison the taste brain with noise. Keep the flag (analytics stay
  true), suppress the signal.
- **The station must survive its own stop button being honest.** `/stop` that clears a queue radio
  instantly refills is an unstoppable bot — the most concrete way SC-2 could fail. D-07 makes `/stop`
  and idle-leave disarm, while keeping `/play` non-destructive: **asking for a song isn't ending the
  station.**
- **The skip button is the hole.** DJ-02 is trivially defeated by a one-click bypass sitting on a
  persistent message. D-15 routes both entry points through one gate — the Phase 20 lesson applied to
  a new surface.
- **"One of two people is not a majority."** D-09c accepts that a duo needs to agree, because
  two-person channels are the common case at this bot's scale and rounding down would mean the
  feature effectively doesn't exist there. The duo-holdout sting is answered by D-13a: you can always
  pull your *own* pick.
- **The tally can't need Gemini.** It fires several times per track, carries live numbers, and must
  work when the 15 RPM budget is exhausted — three independent reasons D-18 is templated. This is
  Critical Rule 12 landing on a UI surface rather than a memory one.
- **Radio and skip democracy are the same argument from two directions.** Radio says the queue
  shouldn't need one person to feed it; skip democracy says it shouldn't obey one person either.
  D-12 (non-destructive start) and D-13b (bot picks always vote) are where that shared principle
  shows up concretely.

</specifics>

<deferred>
## Deferred Ideas

- **Crossfade (DJ-03)** → **Phase 27**, spike-gated, per the roadmap. This phase must not
  pre-commit the playback engine to any crossfade design; Phase 27 sequences after 26 deliberately.
- **Per-guild skip-vote ratio / `/setup` toggles for radio + voting** → rejected for this phase
  (D-21); revisit only if a live server actually wants a different ratio — a schema change plus a
  cache path for a number with a sane default.
- **Weighting a collective vote-skip more heavily than a solo skip in the taste brain** → rejected
  (D-20); revisit only if the existing negative hint proves too weak. Would reopen a subsystem that
  just cleared Phase 25's byte-identical gate.
- **An admin / `manage_guild` skip override** → rejected (D-13a); it reinstates the unilateral power
  DJ-02 removes. Revisit only if a real moderation need appears in a live server.
- **A vote timeout knob** → rejected (D-17); the track boundary already bounds the vote. Revisit only
  if stale half-votes on long tracks prove annoying in live use.
- **Radio persistence across restart** → rejected (D-08); revisit only if the hosting model ever
  becomes always-on (DEPLOY-F1).
- **SQL co-occurrence as a radio source / hybrid engine** → rejected (D-01); a natural revisit if
  Gemini rate-limiting makes radio unreliable in practice, since it costs nothing against the 15 RPM
  budget.
- **Excluding deafened/AFK members from the listener count** → rejected (D-09b); revisit only if a
  deafened member blocking a skip actually happens.
- **A vote-message/button UI for skips** → rejected (D-14); revisit only if `/skip`-as-vote proves
  undiscoverable in live use.

### Reviewed Todos (not folded)
None — `todo.match-phase 26` returned zero matches.

</deferred>

---

*Phase: 26-radio-mode-skip-democracy*
*Context gathered: 2026-07-16*
