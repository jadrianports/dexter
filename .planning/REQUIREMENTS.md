# Requirements: Dexter ("Dex")

> v1 requirements derived from PROJECT.md, intel/constraints.md, intel/context.md, and CLAUDE.md.
> No PRDs were ingested (0 PRD-derived requirements); these are derived from constraints + shipped scope.
> Every requirement maps to exactly one phase. Observable from a user's (or operator's) perspective.

**Core value:** A sarcastic, personality-driven music + AI Discord bot that runs reliably 24/7 — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.

---

## MUSIC — Playback, queue, audio (Phase 1)

| ID | Requirement |
|----|-------------|
| MUSIC-01 | User can `/play` a song by text search and pick from 5 YouTube results via a select menu, then hear it in voice |
| MUSIC-02 | User can `/play` a direct YouTube URL and have it queued without a search menu |
| MUSIC-03 | User can `/play` a playlist URL and have up to 50 tracks queued (truncated + informed beyond 50) |
| MUSIC-04 | User can control playback: `/skip`, `/pause`, `/resume`, `/stop` |
| MUSIC-05 | User can view the queue (`/queue`), shuffle upcoming tracks (`/shuffle`), and set loop mode (`/loop off\|single\|queue`) |
| MUSIC-06 | User can see the current song (`/nowplaying`) and re-play it (`/replay`); a persistent now-playing embed updates on song change |
| MUSIC-07 | Songs over 15 min (`MAX_SONG_DURATION_SECONDS=900`) and livestreams are rejected with a personality message |
| MUSIC-08 | Audio plays from cache (`{video_id}.opus`, opus passthrough) when available, else downloads, else falls back to stream; cache evicts oldest by access time at 2GB cap |
| MUSIC-09 | Bot auto-leaves voice after 10 min idle (`IDLE_TIMEOUT_SECONDS=600`), clearing the queue |
| MUSIC-10 | Per-server queue uses `current_index` (no popping) with generation-counter race prevention; skip always advances regardless of loop mode |
| MUSIC-11 | User can run `/help` to see available commands |

## AI — `/ask`, context, mood, auto-queue, rate limiter (Phase 2)

| ID | Requirement |
|----|-------------|
| AI-01 | User can run `/ask <question>` and receive a Gemini (`gemini-2.0-flash`) response in-character within Discord's timeout (defer + followup) |
| AI-02 | `/ask` responses incorporate the last 10 messages of channel context plus the user's taste summary |
| AI-03 | Mood shifts with daily command count (thresholds 15/30/50) and is injected into the system prompt; seasonal context is injected by date |
| AI-04 | When the queue empties with humans still in voice, the bot AI-auto-queues up to 3 rounds of 3 recommended songs (`was_auto_queued=True`) |
| AI-05 | Auto-queue tracks skip rate ("ignored" memory) and references the outcome on the next auto-queue trigger |
| AI-06 | All AI features share one global 15 RPM rate limiter with priority tiers (user commands wait ≤60s; background/auto-queue rejected if wait >10s) |
| AI-07 | Gemini errors, yt-dlp failures, and unhandled exceptions post to a Discord error-log channel (`ERROR_LOG_CHANNEL_ID`); silently skipped if unset |

## IMG — Image generation (Phase 2)

| ID | Requirement |
|----|-------------|
| IMG-01 | User can run `/imagine <prompt>` and receive a generated image via `gemini-2.5-flash-image` (`response_modalities=["IMAGE"]`) with a sarcastic caption |
| IMG-02 | `/imagine` enforces a daily cap (`MAX_IMAGES_PER_USER_PER_DAY=10`) and logs to `image_generation_log` |
| IMG-03 | A refused/empty image generation returns a personality-flavored refusal instead of an error |

## PERS — Personality system (Phases 2 and 3)

| ID | Requirement | Phase |
|----|-------------|-------|
| PERS-01 | The bot's voice is lowercase, dry, accurate-first-sarcastic-second, ≤500 chars, max one emoji; sarcasm dials back for serious/emotional questions | 2 |
| PERS-02 | The bot roasts users on voice join/leave (30% chance, 5-min per-user cooldown) and complains when moved between channels | 3 |
| PERS-03 | The bot delivers late-night (1-5am) time-related roasts at 50% chance | 3 |
| PERS-04 | The bot always roasts when a user plays the same song 3+ times in one day | 3 |
| PERS-05 | The bot reacts to messages: 👀 on YouTube/Spotify links, 🫡 on "goodnight"/"gn", 😐 on bare mention, deflecting warmth on thanks | 3 |
| PERS-06 | Expanded seasonal awareness injects date-aware personality (December/October/Feb 14/Jan 1/Apr 1) | 3 |
| PERS-07 | Status rotates every 5 min through a pool (current song, server count, personality lines, seasonal) | 3 |
| PERS-08 | The bot posts a startup message on boot and a lonely idle message after 30+ min of no commands while users are in voice | 3 |
| PERS-09 | The bot tracks consecutive-day streaks and total-songs milestones (100/250/500/1000) and roasts on milestone hits | 3 |

## LYRIC / HIST — Lyrics and history commands (Phase 3)

| ID | Requirement |
|----|-------------|
| LYRIC-01 | User can run `/lyrics` to fetch lyrics for the current song (Genius primary, AZLyrics fallback) with pagination |
| HIST-01 | User can run `/history` to view recently queued songs for the server |

## OBS — Production hardening (Phase 2.5)

| ID | Requirement |
|----|-------------|
| OBS-01 | No silent `except Exception` passes: handlers narrow to expected types, `log.exception(...)`, and surface a user-facing error embed where applicable |
| OBS-02 | A playlist import failure always sends a `followup` error embed instead of silently falling through to the single-video path |
| OBS-03 | A first-run cog-load guard mirrors the `on_ready` `GEMINI_API_KEY` check before loading AI cogs |
| OBS-04 | Auto-queue JSON parsing is robust (tolerates fences/prose/object-wrapped arrays, validates `{title, artist}`, logs raw on failure) via a pure testable `parse_suggestions` function |
| OBS-05 | SQLite uses `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout`; `get_recent_songs` binds `LIMIT` as an int |
| OBS-06 | FFmpeg sources are explicitly cleaned up via try/finally when playback never starts or the client is disconnected (no orphans) |
| OBS-07 | yt-dlp self-heals: daily 04:00 `pip install -U yt-dlp` plus on-failure update→retry (throttled ≤once/hour)→stream fallback→error |

## SCALE — Multi-server, persistence, deployment (Phase 4)

| ID | Requirement |
|----|-------------|
| SCALE-01 | The bot is hardened for concurrent multi-server use (DB write contention, queue caps, buffer eviction resolved) |
| SCALE-02 | Persistence migrates SQLite → PostgreSQL (removing SQLite-specific `datetime('now')` usage) |
| SCALE-03 | The bot runs as an `AutoShardedBot` for scale across many guilds |
| SCALE-04 | Music queues persist across restarts |
| SCALE-05 | A hosting/deployment decision is made and the bot runs 24/7 on the chosen provider (the OPEN hosting question is resolved here) |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MUSIC-01 | Phase 1 | Done |
| MUSIC-02 | Phase 1 | Done |
| MUSIC-03 | Phase 1 | Done |
| MUSIC-04 | Phase 1 | Done |
| MUSIC-05 | Phase 1 | Done |
| MUSIC-06 | Phase 1 | Done |
| MUSIC-07 | Phase 1 | Done |
| MUSIC-08 | Phase 1 | Done |
| MUSIC-09 | Phase 1 | Done |
| MUSIC-10 | Phase 1 | Done |
| MUSIC-11 | Phase 1 | Done |
| AI-01 | Phase 2 | Done |
| AI-02 | Phase 2 | Done |
| AI-03 | Phase 2 | Done |
| AI-04 | Phase 2 | Done |
| AI-05 | Phase 2 | Done |
| AI-06 | Phase 2 | Done |
| AI-07 | Phase 2 | Done |
| IMG-01 | Phase 2 | Done |
| IMG-02 | Phase 2 | Done |
| IMG-03 | Phase 2 | Done |
| PERS-01 | Phase 2 | Done |
| OBS-01 | Phase 2.5 | Done |
| OBS-02 | Phase 2.5 | Done |
| OBS-03 | Phase 2.5 | Done |
| OBS-04 | Phase 2.5 | Done |
| OBS-05 | Phase 2.5 | Done |
| OBS-06 | Phase 2.5 | Done |
| OBS-07 | Phase 2.5 | Done |
| PERS-02 | Phase 3 | Complete |
| PERS-03 | Phase 3 | Complete |
| PERS-04 | Phase 3 | Complete |
| PERS-05 | Phase 3 | Complete |
| PERS-06 | Phase 3 | Complete |
| PERS-07 | Phase 3 | Complete |
| PERS-08 | Phase 3 | Complete |
| PERS-09 | Phase 3 | Complete |
| LYRIC-01 | Phase 3 | Complete |
| HIST-01 | Phase 3 | Complete |
| SCALE-01 | Phase 4 | Complete |
| SCALE-02 | Phase 4 | Complete |
| SCALE-03 | Phase 4 | Complete |
| SCALE-04 | Phase 4 | Complete |
| SCALE-05 | Phase 4 | Complete |

**Coverage:** 45/45 v1 requirements mapped to exactly one phase. No orphans, no duplicates.
