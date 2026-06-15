# Dexter ("Dex")

## What This Is

Dexter is a sarcastic, personality-driven Discord bot. It plays music from YouTube (yt-dlp + FFmpeg), chats via Google Gemini (gemini-2.0-flash), and generates images, while tracking user behavior to roast them. The persona is lowercase, dry, accurate-first-sarcastic-second, and uses at most one emoji per message. It is built for a single Discord community as a solo-developer project, with Claude as the implementer. As of v1.0 it is a complete, code-finished bot — music + AI + an "alive" unprompted-behavior layer — hardened and scaled to run 24/7 on PostgreSQL behind an `AutoShardedBot`.

## Core Value

A sarcastic, personality-driven music + AI Discord bot that runs reliably 24/7 — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.

## Current Milestone: v1.1 "Live & Lethal"

**Goal:** Take Dexter from code-complete-on-a-laptop to running 24/7 — fast, polished, and genuinely fun — by deploying it for real, killing playback latency, and surfacing the control, filter, and roast features that make it a joy to use.

**Target features (deploy-first sequencing):**

1. **Ship it live** — Oracle A1 + Postgres + Docker standup, the standing live-UAT checklist (15 behavioral + 6 human scenarios), the parked voice-reconnect race fix (`cogs/music.py:~609`), queue-restore validation across restart, validated `pg_dump` backups + dead-man cron.
2. **Speed & caching** — prefetch the next track (kill the inter-song silence gap), opus-copy instead of opus→opus re-encode, query→video_id resolution cache, wire the dead `DOWNLOAD_TIMEOUT_SECONDS`, least-played eviction (don't depend on `atime` on a `noatime` mount), pipeline timing instrumentation, SponsorBlock segment-skip.
3. **Player UX & filters** — interactive control buttons on the now-playing embed, `/seek`, `/previous`, `/jump`, saveable favorites/personal playlists, `/filter` audio effects (bassboost / nightcore / slowed+reverb / 8d).
4. **Social & personality** — `/roast @user` and `/leaderboard`, built off the existing `user_profiles` / `user_artist_counts` / streak data.
5. **Ops & observability** — `/stats` owner dashboard, health endpoint for the dead-man switch, Gemini/Oracle quota visibility, optional web config dashboard.

**Key context:**
- **Deploy + instrument first** so every speed gain is measured against live numbers, not laptop guesses.
- **One tradeoff to resolve in the roadmap:** `/filter` forces a re-encode, mutually exclusive with opus-copy → opus-copy by default, transcode only when a filter is active per-track.
- **Shelved for a future milestone (v1.2/v2.0):** RAG long-term semantic memory, Vision/multimodal roasting. Considered and deliberately deferred, not rejected.

## Current State

**Shipped: v1.0 MVP (2026-06-12)** — Phases 1, 2, 2.5, 3, 4 complete; all 45 v1 requirements satisfied at the code/structural level. ~7,139 Python LOC across 49 modules, 20 test files, 71 commits.

The bot has been **booted locally only**. Live-deploy validation (Oracle A1 + Postgres + Discord gateway behavioral UAT) is the outstanding day-1 deployment checklist — see STATE.md Deferred Items. No active milestone; next cycle starts with `/gsd-new-milestone`.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ Music playback: `/play` (search + URL + playlist), `/skip`, `/pause`, `/resume`, `/stop`, `/queue`, `/shuffle`, `/loop`, `/nowplaying`, `/replay`, `/help` — v1.0 (Phase 1)
- ✓ Per-server queue model with loop modes, generation-counter race prevention, cache-first audio with stream fallback — v1.0 (Phase 1)
- ✓ `/ask` with Gemini, 10-message context buffer, mood system, user-taste injection, seasonal awareness — v1.0 (Phase 2)
- ✓ `/imagine` with daily cap, AI auto-queue, "ignored" memory, global Gemini rate limiter, Discord error-log channel — v1.0 (Phase 2)
- ✓ Production-honest hardening: unsilenced exception handlers, WAL + busy_timeout, robust auto-queue JSON parse, FFmpeg orphan cleanup, yt-dlp self-heal — v1.0 (Phase 2.5)
- ✓ Unprompted "alive" behavior: voice-join/leave roasts, late-night roasts, repeat-song roasts, emoji reactions, expanded seasonal awareness — v1.0 (Phase 3)
- ✓ Status rotation, startup message, idle-loneliness, streak tracking + milestone roasts, `/lyrics` (Genius + AZLyrics), `/history` — v1.0 (Phase 3)
- ✓ Scale: multi-server hardening, SQLite→PostgreSQL, `AutoShardedBot`, queue persistence, Oracle Cloud A1 hosting decision — v1.0 (Phase 4)

> Phase 3 & 4 items are code-complete and statically verified; their live-behavioral UAT is carried forward as the deployment checklist (STATE.md Deferred Items), not as open scope.

### Active

<!-- Current scope (v1.1 "Live & Lethal"). High-level streams; detailed REQ-IDs live in REQUIREMENTS.md. -->

- [ ] Deploy + live-validate on Oracle A1 (Postgres, Docker, UAT checklist, reconnect race, restart-safe queue restore, backups/cron)
- [ ] Playback speed & caching (prefetch, opus-copy, resolution cache, download timeout, least-played eviction, instrumentation, SponsorBlock)
- [ ] Player UX & filters (control buttons, `/seek`, `/previous`, `/jump`, favorites/playlists, `/filter` effects)
- [ ] Social commands (`/roast @user`, `/leaderboard`)
- [ ] Ops & observability (`/stats` dashboard, health endpoint, quota visibility)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- `/volume` command / `PCMVolumeTransformer` — Discord's per-user volume slider covers it; opus passthrough keeps CPU low
- Prefix commands / hybrid commands — pure `app_commands` slash commands only, by design
- Spotify/Apple Music as audio sources — YouTube via yt-dlp is the single source of truth
- Web config dashboard — listed as "maybe" in Phase 4; not committed scope (reconsider next milestone)
- Live-concurrency-only bugs (e.g. voice reconnect race at `cogs/music.py:~609`) — parked for a dedicated live `/gsd:debug` session once running 24/7; cannot be verified by local boot

## Context

- **v1.0 is code-complete and shipped to `main`.** Layered cog → service → model architecture. Services wired in `bot.py`, attached as bot attributes; cogs access via `self.bot`. CLAUDE.md is the north-star feature spec; `.planning/codebase/` reflects the built state. ~7,139 Python LOC, 49 modules, 20 test files.
- **Bot has been booted locally only.** Every fix was verified by inspection + local boot. Bugs that only manifest under live concurrency are explicitly parked, not fixed blind. The full live-UAT checklist awaits the Oracle A1 VM standup.
- **Personality is the product.** Lowercase, dry, one-emoji-max. Accuracy first, sarcasm second; sarcasm dials back for serious/emotional questions. Mood shifts with daily command count; seasonal context injected into the Gemini system prompt. All personality output is Gemini-first with a guaranteed template fallback.
- **Testing convention:** pure logic gets TDD (`tests/`); Discord/process code (cogs, `bot.py`) is untested-by-design, verified by structural review + clean local boot. Regression gate: full suite green + clean boot with no new silent failures in `dexter.log`.
- **Git convention:** the user handles all git operations (commits, merges, pushes). Do not auto-commit or push.

## Constraints

- **Tech stack**: Python 3.11+, discord.py (+ davey for DAVE voice encryption), yt-dlp + FFmpeg (opus 192kbps), **PostgreSQL via asyncpg** (migrated from SQLite/aiosqlite in Phase 4), Google Gemini via the `google-genai` SDK (NOT the deprecated `google-generativeai`) — fixed per CLAUDE.md, do not deviate
- **AI model**: `GEMINI_MODEL = "gemini-2.0-flash"` for chat; all AI features share a single global 15 RPM rate limiter (`GEMINI_RPM_LIMIT = 15`), priority 1 = user commands (wait ≤60s), priority 2 = background/auto-queue (reject if wait >10s)
- **Image model**: `gemini-2.5-flash-image` with `response_modalities=["IMAGE"]`; `MAX_IMAGES_PER_USER_PER_DAY = 10`
- **Music limits**: `MAX_SONG_DURATION_SECONDS = 900` (reject longer), reject livestreams, `MAX_PLAYLIST_IMPORT = 50` (truncate + inform), `IDLE_TIMEOUT_SECONDS = 600` auto-leave, `AUDIO_CACHE_MAX_MB = 2048` (evict oldest by atime, hourly cleanup), `MAX_QUEUE_SIZE_PER_GUILD = 500` (cap enforced in `MusicQueue.add()`)
- **Reliability**: explicit FFmpeg/voice cleanup on skip/stop/error/leave to avoid orphans; yt-dlp self-heals (daily 04:00 update + on-failure update→retry throttled ≤once/hour→stream fallback→error)
- **Discord interaction timeout**: must `defer()` or respond within 3s, then do async work via `asyncio.create_task()` / `interaction.followup`
- **Hosting**: **RESOLVED → Oracle Cloud Always Free A1 ARM** (Docker Compose for Hetzner portability). Keepalive/dead-man cron + `pg_dump` Object Storage backup. (Carries the known Oracle reclamation/termination risk — monitor in production.)

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Image-gen model = `gemini-2.5-flash-image` (resolved during ingest, not ADR-locked) | Two equal-precedence SPECs diverged; tie broken by ground truth — shipped `config.py:36` | ✓ Good (matches shipped code) |
| Layered cog → service → model architecture, services wired in `bot.py` | Decoupling, testability of pure logic, "grow into the spec" | ✓ Good |
| `current_index` queue (no popping) instead of pop-on-play | Enables `/replay`, `/previous`, loop wrap, `/history` | ✓ Good |
| Global Gemini rate limiter with priority tiers (sliding-window deque) | All AI features share one 15 RPM budget; user commands must not starve | ✓ Good |
| Phase 2.5 parks live-concurrency bugs rather than fixing blind | Bot booted locally only; fixes must be verifiable by inspection + local boot | ✓ Good |
| Hosting → Oracle Cloud Always Free A1 ARM (Phase 4) | Always-free ARM capacity fits a single-community bot; Docker Compose keeps Hetzner portability open | ✓ Resolved — ⚠ monitor reclamation/termination risk in production |
| Persistence → PostgreSQL via asyncpg 0.31.0 (Phase 4) | SQLite sufficient for v1–v3; multi-server scale needs real concurrency + durable queue persistence; raw `CREATE TABLE IF NOT EXISTS` over Alembic for a start-fresh schema | ✓ Resolved (static); live round-trip pending deploy |
| Queue cap enforced in `MusicQueue.add()` (Phase 4) | Guard at the source covers the playlist loop and every add path automatically | ✓ Good |
| Gemini-first personality output with guaranteed template fallback (Phase 3) | Never let rate limits or API errors block a roast/response | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-12 after v1.1 "Live & Lethal" milestone kickoff*
