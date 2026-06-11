# Phase 3: Alive - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered
> and the canonical voice samples.

**Date:** 2026-06-11
**Phase:** 3-alive
**Areas discussed:** Roast source / Voice, Post channel, Roast intensity, Lyrics & history, Streak mechanics

---

## Roast source / Voice

The bulk of the discussion. User flagged up front: *"i don't really think the system prompt translated well to the personality i want."* Diagnosed root cause: the shipped `DEXTER_SYSTEM_PROMPT` is an adjective list with **zero few-shot examples**, so Gemini defaults to a generic helpful-assistant voice.

The voice converged through four user corrections:
1. **"sharper / meaner... almost like deadpool"** → cranked edge, added fourth-wall awareness.
2. **"personality being self aware bot is kinda cringe"** → cut ALL bot-self-awareness/fourth-wall.
3. **"the low self esteem self deprecating thing is kinda cringe... roast users not itself"** → cut self-deprecation.
4. **"tune up the meanness... a little"** → raised the meanness ceiling.

| Decision point | Options | Selected |
|---|---|---|
| Direction from samples | This is it / Sharper-meaner / Warmer-weirder / Not specific enough | **Sharper / meaner ("like deadpool")** |
| Language level | Mild swearing / Full Deadpool / Clean but savage / Censored f-bombs | **Mild swearing** |
| Roast source | Hybrid / Templates only / Gemini-generated | **Hybrid** |
| Residual voice gap | Fixed it / Too wordy / Drop pop-psych / Not my taste | **Drop the pop-psych** |
| Meanness ceiling | Lock here / Push meaner / One tweak | **Lock here** |

**Final standard:** arrogant + superior, dry, contempt aimed **outward and down only**, mild swearing, humor from **specific user-data recall**. Three banned inward modes: (1) bot self-awareness, (2) pop-psych diagnosis, (3) self-deprecation. Lowercase / ≤500 chars / one-emoji-max / accurate-first preserved. System prompt to be rewritten WITH few-shot exemplars.

### Voice samples (canonical register reference — seed for template pools / few-shot prompt)

**Join (with data):** `marcus. back with the drake. forty-seven plays last week. one artist, one emotion, zero growth. impressive commitment to being boring.` · `back already. your top artist this month is morgan wallen. i'm not mad, i'm embarrassed for you.` · `two hours of phonk last night at a volume that sounded like a dishwasher dying. do it again, i dare you.`

**Join (new face):** `new person. queue one song and i'll have your whole taste figured out. you won't like the summary.`

**Late night (1–5am):** `it's 3am. nothing good gets queued at 3am and you're about to prove it.` · `4am. the only things awake right now are you, me, and your regrets. pick something.`

**Last to leave:** `and they're gone. the average taste in this channel just doubled.` · `everyone left. good. the queue's been dragged through hell today, it needed the break.`

**Moved channel:** `you moved me mid-song. for what. couldn't sit still ninety seconds, could you.`

**Same song 3+/day:** `five plays of the same song today. it was mediocre the first time. you've just been marinating in it.` · `sixth time. it didn't deserve the first play, let alone six.`

**Milestone (songs):** `1000 songs queued and not one of them good. genuinely a feat. 🎉` · `100th song. mostly drake, some morgan wallen. a milestone built entirely on bad decisions.`

**Streak:** `45 days straight and your taste hasn't improved a single inch. consistency, i guess.` · `your record's 30 days. let's see you choke before then.`

**Idle:** `thirty minutes of silence. best this queue has sounded all week. keep it up.`

**Startup:** `i'm back. the queue fell apart without me, obviously. let's see what damage you did.`

**Thanks → deflect:** `...you're welcome. don't get used to it.`

**Status pool:** `judging your playlist` · `playing for {n} servers that don't deserve me` · `{current_song}, regrettably` · `now playing: a mistake` · `tolerating your taste`

**Seasonal:** *Dec:* `it's december. queue one mariah carey and i'm pulling the plug on this whole operation. try me.` · *Feb 14:* `valentine's day and you're in here queueing sad songs alone. i'd console you but it's funnier not to.` · *Jan 1:* `new year, same garbage queue as last year. didn't even pretend to change.` · *Apr 1:* `april first. that song you love? everyone mutes when you queue it. that part's true year-round.`

**Auto-queue ignored:** `last time you skipped every pick i made — bold, from someone whose top song is a tiktok snippet. here's three more. keep up.`

**Banned (examples of what NOT to write):** `i'm a piece of software and even i'm bored` (bot-meta) · `at what point is this a personality and not a playlist` (pop-psych) · `did you miss me. probably not.` (self-deprecation).

---

## Post channel

| Option | Description | Selected |
|--------|-------------|----------|
| Designated + fallback | `DEXTER_CHANNEL_ID`; if unset → music channel → system → first writable | ✓ |
| Follow the activity | Always post to last-active music channel | |
| Dedicated channel only | Only `DEXTER_CHANNEL_ID`; silent if unset | |

**Notes:** Applies to ambient posts (join/leave roasts, startup, idle). Reactions attach to the message; repeat-song/milestone roasts post to the music channel where they fire.

---

## Roast intensity

| Option | Description | Selected |
|--------|-------------|----------|
| Spec odds + global ceiling | Specced chances + ONE unified per-user ambient cooldown; earned roasts bypass | ✓ |
| Spec odds, no ceiling | Per-trigger cooldowns only, can stack | |
| More aggressive | Raise odds / shorten cooldowns | |
| Restrained / rarer | Lower odds + ceiling | |

**Notes:** Ambient roasts (join/leave/late-night) share ~1-per-5–10-min per-user budget. Repeat-song (3+) and milestones always fire (earned, bypass ceiling).

---

## Lyrics & history

| Command | Options | Selected |
|---|---|---|
| `/lyrics` target | Current song only / Current + optional query | **Current song only** |
| `/history` scope | Server-wide / Per-user / Server + user filter | **Server-wide** |

**Notes:** Both reuse `QueuePageView` button pagination and fall back to a personality message on empty/not-found. Genius API doesn't serve lyrics text directly → search-then-scrape, AZLyrics fallback.

---

## Streak mechanics (additional area, user chose to dig in)

| Decision point | Options | Selected |
|---|---|---|
| Day boundary | Single configured timezone / UTC / Per-user tz | **Single configured timezone (`STREAK_TIMEZONE`)** |
| Reset rule | Strict (miss a day → 1) / One-day grace | **Strict** |
| Streak memory | Milestones + longest-streak / + broken-streak roast / Minimal | **Milestones + track longest_streak** |

**Notes:** New `user_profiles` columns (`current_streak`, `longest_streak`, `last_streak_date`). Milestones: songs `[100,250,500,1000]`, streak-days `[7,14,30,60,100]`, always-fire once per threshold.

---

## Claude's Discretion

- Exact wording of all template-pool lines (user reviews during execution; this phase locked the *voice standard*, not final copy).
- Exact config values (ambient ceiling window, `STREAK_TIMEZONE` default, status interval, idle threshold), page sizes, embed layouts.
- Genius lookup implementation (raw scrape vs `lyricsgenius` library).
- Which additional seasonal dates to add beyond the existing 5.

## Deferred Ideas

- Streak-broken roast (beyond PERS-09 wording).
- Per-user streak timezones (Phase 4 scale).
- One-day "streak freeze" grace.
- `/lyrics` arbitrary-song query arg.
- `/history` per-user filter.
