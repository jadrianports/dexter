# Roadmap: Dexter ("Dex")

## Overview

Dexter starts as a reliable YouTube music player, grows a Gemini-powered sarcastic personality with `/ask` and `/imagine`, gets a production-honest hardening pass so it survives 24/7 without silent failures or orphaned FFmpeg processes, then comes alive with unprompted roasts, reactions, lyrics, and history before finally scaling beyond a single server. Phases 1, 2, and 2.5 are already shipped; Phase 3 ("Alive") is the next work, and Phase 4 ("Scale") closes out the open hosting/deployment question.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Music MVP** - YouTube playback, queue model, cache-first audio, idle leave
- [x] **Phase 2: Personality + AI** - `/ask`, `/imagine`, mood, auto-queue, global rate limiter
- [x] **Phase 2.5: Hardening** - Production-honest reliability pass (observability, WAL, FFmpeg cleanup, yt-dlp self-heal)
- [x] **Phase 3: Alive** - Unprompted roasts, reactions, seasonal, status, streaks, `/lyrics`, `/history` (completed 2026-06-11)
- [ ] **Phase 4: Scale** - Multi-server, PostgreSQL, sharding, queue persistence, hosting decision

## Phase Details

### Phase 1: Music MVP

**Goal**: A working sarcastic-branded YouTube music player with a robust per-server queue
**Depends on**: Nothing (first phase)
**Requirements**: MUSIC-01, MUSIC-02, MUSIC-03, MUSIC-04, MUSIC-05, MUSIC-06, MUSIC-07, MUSIC-08, MUSIC-09, MUSIC-10, MUSIC-11
**Success Criteria** (what must be TRUE):

  1. User can `/play` a song by search (5-result select menu) or direct URL and hear it in voice
  2. User can `/play` a playlist URL and have up to 50 tracks queued, truncated + informed beyond 50
  3. User can `/skip`, `/pause`, `/resume`, `/stop`, `/queue`, `/shuffle`, `/loop`, `/nowplaying`, `/replay`, and `/help`
  4. Songs over 15 min and livestreams are rejected with a personality message; audio plays cache-first with stream fallback
  5. Bot auto-leaves voice after 10 min idle and clears the queue

**Plans**: Complete (shipped)
**Status**: Complete ✓

### Phase 2: Personality + AI

**Goal**: Dexter gains its Gemini-powered personality, conversational `/ask`, image generation, and self-feeding music recommendations
**Depends on**: Phase 1
**Requirements**: AI-01, AI-02, AI-03, AI-04, AI-05, AI-06, AI-07, IMG-01, IMG-02, IMG-03, PERS-01
**Success Criteria** (what must be TRUE):

  1. User can `/ask <question>` and get an in-character Gemini response that uses the last 10 messages of context and their taste summary
  2. Bot mood shifts with daily command count (15/30/50 thresholds) and seasonal context is injected into the prompt
  3. User can `/imagine <prompt>` and get a `gemini-2.5-flash-image` image (or a personality refusal), capped at 10/day
  4. When the queue empties with humans in voice, the bot auto-queues recommended songs and remembers when they get skipped
  5. All AI calls share one 15 RPM rate limiter with priority tiers, and errors post to the Discord error-log channel

**Plans**: Complete (shipped)
**Status**: Complete ✓

### Phase 2.5: Hardening

**Goal**: A production-honest reliability pass so the bot survives unattended running without silent failures or orphaned processes
**Depends on**: Phase 2
**Requirements**: OBS-01, OBS-02, OBS-03, OBS-04, OBS-05, OBS-06, OBS-07
**Success Criteria** (what must be TRUE):

  1. No silent `except Exception` passes remain — failures are narrowed, logged via `log.exception`, and surfaced to the error channel/embed
  2. Playlist import failures always send a followup error embed; first-run cog loading is guarded by the `GEMINI_API_KEY` check
  3. Auto-queue JSON parsing is robust against fences/prose/object-wrapping via a pure testable `parse_suggestions` and validates `{title, artist}`
  4. SQLite runs with WAL + `busy_timeout` and binds `LIMIT` as an int; FFmpeg sources are explicitly cleaned up when playback never starts
  5. yt-dlp self-heals via a daily 04:00 update plus a throttled on-failure update→retry→stream-fallback→error chain

**Plans**: Complete (shipped)
**Status**: Complete ✓

### Phase 3: Alive

**Goal**: Dexter feels present — it reacts, roasts unprompted, tracks habits, and exposes lyrics and history
**Depends on**: Phase 2.5
**Requirements**: PERS-02, PERS-03, PERS-04, PERS-05, PERS-06, PERS-07, PERS-08, PERS-09, LYRIC-01, HIST-01
**Success Criteria** (what must be TRUE):

  1. Bot roasts users unprompted on voice join/leave (with cooldown), late at night (1-5am), and when the same song is replayed 3+ times in a day
  2. Bot reacts to messages (👀 on links, 🫡 on goodnight, 😐 on bare mention) and shows expanded seasonal awareness
  3. Bot rotates its status every 5 min, posts a startup message, and posts a lonely idle message after long silence with users in voice
  4. Bot tracks consecutive-day streaks and total-songs milestones (100/250/500/1000) and roasts on milestone hits
  5. User can run `/lyrics` (Genius primary, AZLyrics fallback, paginated) and `/history` for recently queued songs

**Plans**: 6 plans (3 waves)Plans:
**Wave 1**

- [x] 03-01-PLAN.md — Foundation: Phase 3 config constants, personality/roasts.py template pools, DEXTER_SYSTEM_PROMPT few-shot rewrite [wave 1]
- [x] 03-02-PLAN.md — Streak DB migration + pure compute_streak + repeat-song/streak/history DB helpers [wave 1]
- [x] 03-03-PLAN.md — LyricsService (Genius + AZLyrics fallback) + pure lyrics helpers + deps [wave 1]

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-04-PLAN.md — EventsCog: voice join/leave/move roasts, reactions, expanded seasonal [wave 2]
- [x] 03-05-PLAN.md — MusicCog: /lyrics, /history, repeat-song + streak/milestone roasts [wave 2]

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 03-06-PLAN.md — bot.py: status rotation, startup message, idle-loneliness, lyrics wiring [wave 3]

**Status**: Code-complete (10/10 must-haves verified; live Discord UAT pending)

### Phase 4: Scale

**Goal**: Dexter runs reliably across many servers on chosen 24/7 hosting with durable persistence
**Depends on**: Phase 3
**Requirements**: SCALE-01, SCALE-02, SCALE-03, SCALE-04, SCALE-05
**Success Criteria** (what must be TRUE):

  1. Bot handles concurrent multi-server use without DB write contention, unbounded queues, or buffer-eviction issues
  2. Persistence runs on PostgreSQL with no SQLite-specific `datetime('now')` dependence
  3. Bot runs as an `AutoShardedBot` and restores music queues across restarts
  4. A hosting/deployment decision is resolved and the bot runs 24/7 on the chosen provider

**Plans**: 5 plans (3 waves)
**Wave 1**

- [x] 04-01-PLAN.md — Pure-logic spine: queue cap (QueueFullError), Track to_dict/from_dict, MessageBuffer TTL eviction, Phase 4 config constants + unit tests [wave 1] (2026-06-12)
- [ ] 04-02-PLAN.md — database.py aiosqlite→asyncpg full rewrite (Postgres DDL incl. guild_queues, log_track_batch transaction), requirements swap, integration tests [wave 1]

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 04-03-PLAN.md — bot.py: AutoShardedBot swap, asyncpg pool + _ready_once guard, queue_persistence service (persist + smart-rejoin restore) [wave 2]
- [ ] 04-05-PLAN.md — Infra: Dockerfile + docker-compose (arm64, Postgres, volumes), keep-alive/dead-man + pg_dump backup scripts, .env.example (Oracle A1 hosting decision) [wave 2]

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 04-04-PLAN.md — Cog consumers: db→pool migration (music/ai/imagine), batched /play logging, queue-cap rejection, persist-on-mutation hooks + voice-channel-id capture [wave 3]

**Status**: Executing (1/5 plans complete)

> Out of committed scope (per PROJECT.md): web config dashboard ("maybe" only), and the live-concurrency reconnect race (`cogs/music.py:~609`) parked for a dedicated live `/gsd:debug` session once running 24/7.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 2.5 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Music MVP | 100% | Complete | 2026-04-12 |
| 2. Personality + AI | 100% | Complete | 2026-04-13 |
| 2.5. Hardening | 100% | Complete | 2026-06-02 |
| 3. Alive | 6/6 | Complete   | 2026-06-11 |
| 4. Scale | 1/5 | Executing | - |
