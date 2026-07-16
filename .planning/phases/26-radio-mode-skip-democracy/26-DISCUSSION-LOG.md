# Phase 26: Radio Mode & Skip Democracy - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-16
**Phase:** 26-radio-mode-skip-democracy
**Areas discussed:** Radio's engine & seed, Radio's control & lifecycle, Skip vote threshold, Vote mechanics & narration, plus cross-cutting (pure seam, taste interaction, config scope)

**Session shape:** User selected all four presented gray areas, chose "More questions" twice (radio
engine, radio lifecycle) and "Explore more gray areas" once after the four areas closed. Every
question was answered with the recommended option — an affirmative selection, not an AFK adoption.

---

## Area selection

| Option | Description | Selected |
|--------|-------------|----------|
| Radio's engine & seed | What generates the endless stream; what a seed is | ✓ |
| Radio's control & lifecycle | On/off surface, disarm triggers, persistence, refill timing | ✓ |
| Skip vote threshold | Majority vs fixed count; who counts; who bypasses | ✓ |
| Vote mechanics & narration | How votes are cast; the button; tally; expiry | ✓ |

---

## Radio's engine & seed

### Q1 — What generates radio's endless stream of tracks?

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse Gemini auto-queue (Recommended) | try_auto_queue with the 3-round cap lifted + seed anchor; inherits taste blend, skip hint, hallucination validator. Cost: priority-2 chat per refill, rejected when limiter wait >10s | ✓ |
| SQL co-occurrence only (/discover engine) | Zero Gemini cost, can't hallucinate, no RPM exposure — but only knows artists THIS guild already played together; fresh servers dry up; returns artists not tracks | |
| Hybrid: SQL first, Gemini fallback | Best coverage, cheapest in established servers — but two engines to build, tune, test; two quality bars in one feature | |

**User's choice:** Reuse Gemini auto-queue → **D-01**

### Q2 — How should the seed steer recommendations?

| Option | Description | Selected |
|--------|-------------|----------|
| Seed anchors, context stays (Recommended) | Seed added as an anchor line to existing recent-history + room-taste prompt; drifts naturally like real radio; reuses build_recommendation_prompt with one added slot | ✓ |
| Seed replaces the history context | Pure "artist radio", never drifts — but throws away the taste brain and gets repetitive | |
| Seed anchors + explicit drift control | Most flexible — but a tuning knob with no obvious right value and no live UAT to feel it out | |

**User's choice:** Seed anchors, context stays → **D-02**

### Q3 — How do we stop radio recycling tracks over a long session?

| Option | Description | Selected |
|--------|-------------|----------|
| Session played-set + hard post-filter (Recommended) | Track queued video_ids; prompt hint + independent post-resolution rejection. Mirrors Phase 14 D-02 — Gemini's compliance is never the guarantee | ✓ |
| Prompt hint only (no post-filter) | Simpler — but trusts the model as the only guard, the exact thing the hallucination validator exists because Gemini doesn't do | |
| Rely on existing recent-10 history | Zero code — but a long session visibly cycles, undermining DJ-01's promise | |

**User's choice:** Session played-set + hard post-filter → **D-03**

### Q4 — What happens when a priority-2 refill is rejected/empty?

| Option | Description | Selected |
|--------|-------------|----------|
| Retry next cycle, stay silent (Recommended) | Log and do nothing visible; radio stays armed. Matches try_auto_queue's existing empty-response handling. Risk: a fully drained queue goes quiet unexplained | ✓ |
| Narrate each failed refill | Honest and in-character — but fires repeatedly on a busy budget and exposes quota mechanics | |
| Escalate radio to priority 1 | Radio always works — at the cost of starving /ask and roasts | |

**User's choice:** Retry next cycle, stay silent → **D-04**

### Q5 (after "More questions") — How should radio tracks be marked?

| Option | Description | Selected |
|--------|-------------|----------|
| Marked auto-queued, ignored-signal suppressed (Recommended) | Keep was_auto_queued=True (analytics stay true); gate off the auto_queue_ignored memory write + announce while radio is armed. Skipping during radio is channel-surfing, not a taste verdict | ✓ |
| Marked auto-queued, everything fires as-is | Zero new branches — but an hour of radio writes a stream of ignored memories and nags the room | |
| Not marked auto-queued at all | No nagging — but silently breaks /skips analytics and hides radio from song_history | |

**User's choice:** Marked auto-queued, ignored-signal suppressed → **D-05**

### Q6 — How does Dexter parse track-vs-artist in a seed?

| Option | Description | Selected |
|--------|-------------|----------|
| One free-text seed, Gemini interprets (Recommended) | Single optional string into the anchor slot; default to now-playing track, then recent history. No parsing; a misread costs nothing since the validator still gates every queued track | ✓ |
| Explicit track vs artist choice | Unambiguous — but a clunkier surface for a value that becomes one line of prompt text | |
| Resolve the seed through YouTube first | Grounds the seed — but spends a search per start and forces a track reading onto an artist request | |

**User's choice:** One free-text seed, Gemini interprets → **D-06a**

---

## Radio's control & lifecycle

### Q1 — Command surface?

| Option | Description | Selected |
|--------|-------------|----------|
| /radio start [seed] + /radio stop (Recommended) | Subcommand group matching /playlist, /jam, /memory, /setup, /guilds. Sidesteps the trap where a seed of "off"/"stop" is indistinguishable from an artist named that | ✓ |
| /radio [seed] with an on\|off choice arg | Mirrors /autolyrics — but crams two argument kinds into one command | |
| A flag on /play | Ties seed to a resolved track — but buries the headline feature and gives it no natural "off" | |

**User's choice:** /radio start + /radio stop → **D-06b**

### Q2 — What disarms radio besides /radio stop?

| Option | Description | Selected |
|--------|-------------|----------|
| /stop + idle-leave disarm; /play just injects (Recommended) | /stop must disarm or it clears a queue radio instantly refills — an unstoppable bot, the clearest SC-2 violation. But /play mid-radio only injects: asking for a song isn't ending the station | ✓ |
| Any human /play also disarms | Mirrors today's auto_queue_rounds reset — but one person adding one song silently kills a mode nobody asked to end | |
| Only /radio stop ever disarms | Predictable — but /stop becomes a lie, which IS the leftover-refill failure SC-2 prevents | |

**User's choice:** /stop + idle-leave disarm; /play injects → **D-07**

### Q3 — Where does radio state live? Does it survive restart?

| Option | Description | Selected |
|--------|-------------|----------|
| In-memory, dies on restart (Recommended) | Lives on MusicQueue/ServerState like auto_lyrics; no persistence, no schema change. Honest given on-demand hosting: the bot going down IS the session ending. No ghost radio on restore | ✓ |
| Persisted in guild_queues JSONB, restored | Nicer continuity — but a crashed bot could come back and autonomously queue into a room; adds to the scar-heavy restore path | |
| In-memory + explicit teardown clearing | Safer against a stale flag — though arguably just the implementation of option 1 | |

**User's choice:** In-memory, dies on restart → **D-08**

### Q4 — When does radio refill?

| Option | Description | Selected |
|--------|-------------|----------|
| Lookahead — refill while tracks remain (Recommended) | Refill at N-remaining, checked at _on_track_end. Prefetch keeps working so radio is gapless. On-empty would stall on Gemini + YouTube at every boundary — dead air, undoing Phase 6 | ✓ |
| On-empty — reuse the existing trigger | Least new code — but every refill is a hole in the audio | |
| Time-based background refill loop | Decouples refill from playback — but races the playback engine and generation counter for no benefit | |

**User's choice:** Lookahead — refill while tracks remain → **D-10**

### Q5 (after "More questions") — Radio vs loop mode?

| Option | Description | Selected |
|--------|-------------|----------|
| /radio start turns loop off; /loop disarms radio (Recommended) | Mutually exclusive, each announces it. LoopMode.QUEUE never exhausts (radio piles forever); SINGLE never advances (radio frozen). clear() already resets loop_mode | ✓ |
| Radio wins silently — loop ignored while on | Fewer moving parts — but /loop and the embed's Loop field would report a mode not in effect: a lie in the UI | |
| Let them coexist | Least code — but emergent behavior is genuinely bad; a bug report, not a feature | |

**User's choice:** Mutually exclusive, each announces → **D-11**

### Q6 — /radio start with an existing queue?

| Option | Description | Selected |
|--------|-------------|----------|
| Keep the queue, radio takes over at the end (Recommended) | Existing tracks play out; radio refills behind them at the lookahead threshold. Non-destructive; reuses the same refill path with no special "starting" case | ✓ |
| Clear the queue and start fresh | Instant obvious response — but destroys others' queued tracks, precisely the hijacking problem DJ-02 fixes in this same phase | |
| Refuse until the queue is empty | Safest — but makes the headline feature annoying to start for a conflict with a good non-destructive answer | |

**User's choice:** Keep the queue, radio takes over at the end → **D-12**

---

## Skip vote threshold

### Q1 — Which rule decides when a skip fires?

| Option | Description | Selected |
|--------|-------------|----------|
| Majority of listeners, ratio configurable (Recommended) | Computed live from non-bot voice members, fraction as a config knob. Satisfies both readings of the criterion. A fixed count can't: 2 votes is unanimity in a duo, trivial in a party of twelve | ✓ |
| Fixed configurable count | Simple and predictable — but wrong at both ends of the room-size range | |
| Majority with an upper cap | Handles a 20-person channel — a knob defending a hypothetical at this scale | |

**User's choice:** Majority of listeners, ratio configurable → **D-09**

### Q2 — Who counts as a listener?

| Option | Description | Selected |
|--------|-------------|----------|
| Every non-bot member in voice (Recommended) | Reuse the exact enumeration _on_track_end and the taste blend already use. One definition of "who's in the room"; a self-muted member is still listening | ✓ |
| Exclude self-deafened members | More correct in principle — but forks the listener definition for a rare case | |
| Exclude deafened and AFK members | Most accurate — most new state to read, test, and keep in sync | |

**User's choice:** Every non-bot member in voice → **D-09b**

### Q3 — Rounding at 2 listeners?

| Option | Description | Selected |
|--------|-------------|----------|
| Strict majority — more than half (Recommended) | 2→2, 3→2, 4→3. One of two people is not a majority; keeps the gate meaningful at the room sizes Dexter actually runs in. Tradeoff: a duo holdout blocks every skip | ✓ |
| Round down — half, floored | 2→1, 3→2, 4→2. Skips stay easy — but a duo gets zero democracy, and duos are the common case, so the feature mostly wouldn't exist | |
| Strict majority, duo needs only 1 | Optimizes each room size for feel — at the cost of a hardcoded exception in one line of arithmetic | |

**User's choice:** Strict majority → **D-09c**

### Q4 — Who bypasses the vote?

| Option | Description | Selected |
|--------|-------------|----------|
| The track's requester only (Recommended) | Track.requested_by already exists, so it's free. Retracting your own song isn't a hijack; it's the escape from the duo-holdout case. No admin override — that would reinstate the power DJ-02 removes | ✓ |
| Requester + manage_guild admins | Practical for moderation — but the loudest admin still owns the queue | |
| Nobody bypasses — pure democracy | Clean and least code — but you can't withdraw your own misclick, and a duo holdout locks the queue | |

**User's choice:** The track's requester only → **D-13a**

### Q5 — Do bot-queued (radio/auto-queue) tracks vote?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — bot-queued tracks always vote (Recommended) | requested_by = bot.user.id, so D-13a falls through with zero special-casing. Nobody chose the track, so nobody retracts it; Dex's own picks are exactly what a room should have a say on | ✓ |
| No — bot-queued tracks skip instantly | Keeps radio responsive — but skip democracy effectively switches off during radio, the session where the queue is most shared | |

**User's choice:** Yes — bot-queued tracks always vote → **D-13b**

---

## Vote mechanics & narration

### Q1 — How does a listener cast a vote?

| Option | Description | Selected |
|--------|-------------|----------|
| /skip is the vote (Recommended) | One vote per distinct user, idempotent. No new UI or message lifetime; it's what people already type. SKIP_COOLDOWN_SECONDS=2 stays as anti-spam | ✓ |
| First /skip posts a vote message with a button | Visually obvious — but adds a view lifetime to tear down per track; the persistent-view rules target durable controls, not ephemeral polls | |
| Reaction-based voting on the now-playing embed | Lightweight-feeling — but a separate event path with races, colliding with the embed's delete-and-resend cycle | |

**User's choice:** /skip is the vote → **D-14**

### Q2 — What happens to the ⏭ Skip button?

| Option | Description | Selected |
|--------|-------------|----------|
| Both routes through one vote choke point (Recommended) | Button press = a vote, same gate as /skip. Follows Phase 20 OWNER-05. The alternative leaves a one-click bypass on a persistent message, making the gate decorative | ✓ |
| Button skips instantly, only /skip votes | Zero risk to the view — but DJ-02 is trivially defeated by clicking instead of typing: a hole | |
| Remove the button when multiple listeners present | Unambiguous — but mutating view children from live voice state is more moving parts than one shared gate | |

**User's choice:** Both routes through one vote choke point → **D-15**

### Q3 — Who sees the tally?

| Option | Description | Selected |
|--------|-------------|----------|
| Public tally, in Dex's voice (Recommended) | "2 of 3. one more and this track's gone." A vote nobody can see isn't democracy — the room must know a vote is open to join it. Bounded at one line per listener per track | ✓ |
| Ephemeral to voter, public only on success | Zero noise — but nobody knows a vote is open, so the second vote never comes and the feature quietly fails | |
| Edit one tally message in place | Cleanest channel — but another per-track message lifetime colliding with the now-playing resend cycle | |

**User's choice:** Public tally, in Dex's voice → **D-16**

### Q4 — When do votes reset or expire?

| Option | Description | Selected |
|--------|-------------|----------|
| Reset on track change; threshold recomputed live (Recommended) | Votes scoped to the current track; requirement derived at each vote from who's in voice. No timeout knob — the track ending IS the timeout. A leaver's vote stays counted so a walkout can't strand a vote | ✓ |
| Reset on track change + a vote timeout | Stops a stale half-vote on a long track — but another knob with no right value and no UAT to tune it | |
| Reset on track change; drop votes when a voter leaves | Most principled — but needs on_voice_state_update wired into vote state and can confusingly decrement mid-vote | |

**User's choice:** Reset on track change; threshold recomputed live → **D-17**

### Q5 — Where does the tally text come from?

| Option | Description | Selected |
|--------|-------------|----------|
| Templated responses, code-interpolated numbers (Recommended) | A personality/responses.py pool, counts formatted by code — the AUTO_QUEUE_ANNOUNCE pattern. Honors Critical Rule 12 structurally, costs nothing against 15 RPM, works when rate-limited. A vote fires several times per track and can't depend on the AI | ✓ |
| Gemini-generated with the tally passed in | Freshest personality — but a chat call per vote, needs a fallback anyway, and hands the model numbers it could restate wrong | |
| Templated, Gemini flourish on the final skip only | Caps cost at one call per skip — but two narration paths for a line most people barely read | |

**User's choice:** Templated, code-interpolated numbers → **D-18**

---

## Cross-cutting (user chose "Explore more gray areas")

### Q1 — What lands in logic/ for this phase?

| Option | Description | Selected |
|--------|-------------|----------|
| Both: a radio seam + a skip-vote seam (Recommended) | Radio's refill gate and the vote decision both become pure keyword-only functions; cogs dispatch on the result. Both hold real branching logic trapped behind Discord objects; the vote rule especially needs mock-free tests to lock SC-3/SC-4 | ✓ |
| Skip-vote seam only | The vote rule clearly belongs; radio's gate looks thin — but it isn't once armed-state + lookahead + played-set combine, and that's the SC-1/SC-2 logic | |
| Let the planner decide per feature | Flexible — but 5 phases of precedent say decision logic gets extracted; leaving it open invites the one answer the convention rules out | |

**User's choice:** Both seams → **D-19**

### Q2 — Should a vote-skipped radio track feed the taste brain differently?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — mark_song_skipped as today, no new signal (Recommended) | Flows into the existing negative hint like any skip. No new memory kind or weighting; a room voting a track down is already strong signal the existing plumbing carries | ✓ |
| Yes, and weight a voted skip higher | Appealing — but a new weighting concept in a subsystem that just cleared Phase 25's byte-identical gate, for a signal already captured | |
| No — don't record vote-skips as taste signal | Keeps the taste brain clean — but suppressing mark_song_skipped breaks /skips analytics and skip history predating this phase | |

**User's choice:** Existing mark_song_skipped, nothing more → **D-20**

### Q3 — Do these features need per-guild config?

| Option | Description | Selected |
|--------|-------------|----------|
| No new per-guild config — global knobs only (Recommended) | Both are user-invoked music commands, not unprompted ambient surfaces. The AmbientSurface machinery gates what Dexter does unprompted at strangers; these are already governed by the Phase 20 interaction_check choke point | ✓ |
| Add /setup toggles for radio and skip-voting | Consistent with v1.4's philosophy — but schema + cache surface for features with none of the abuse risk that motivated per-guild gating | |
| Skip-vote ratio configurable per guild | The one knob where server culture varies — but a schema change for a number with a sane default and no UAT proving servers want it different | |

**User's choice:** No new per-guild config → **D-21**

---

## Claude's Discretion

Per the standing Phase 11/13/14/15/16/17/21/25 discretion-on-numbers precedent, the user was not
asked about (and downstream agents must not re-ask):

- All numeric knobs: majority ratio default, lookahead depth, refill batch size, session played-set cap
- Where radio's armed state lives (MusicQueue vs ServerState) — must not be persisted (D-08)
- How the round cap is lifted (branch / keyword-only param / shared refill core) — auto-queue must
  stay byte-identical when radio is disarmed
- Exact logic/ module names and signatures for the two D-19 seams
- Exact shape of the D-15 shared skip choke point (one gate, both routes)
- How the D-05 ignored-signal suppression is expressed
- Whether the D-02 seed anchor is a new optional param on build_recommendation_prompt (strongly
  preferred, per the Phase 14 precedent) or a separate builder
- Exact test shape (mock-free for both pure seams; glue untested-by-design per TESTING.md)
- Wording of all new personality copy (tally pool, radio start/stop/disarm, loop-exclusion notices)

## Deferred Ideas

- Crossfade (DJ-03) → Phase 27, spike-gated — this phase must not pre-commit the engine
- Per-guild skip-vote ratio / /setup toggles → rejected (D-21)
- Weighting collective vote-skips more heavily in the taste brain → rejected (D-20)
- Admin/manage_guild skip override → rejected (D-13a)
- A vote timeout knob → rejected (D-17)
- Radio persistence across restart → rejected (D-08); revisit only if hosting becomes always-on
- SQL co-occurrence / hybrid radio engine → rejected (D-01); natural revisit if rate-limiting makes
  radio unreliable
- Excluding deafened/AFK members from the listener count → rejected (D-09b)
- A vote-message/button UI for skips → rejected (D-14)
