---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Live & Lethal
status: completed
stopped_at: Completed 07-04 user_playlists + /playlist group — 2 tasks (3 commits incl. TDD RED/GREEN), playlists table + save/load/list/delete commands
last_updated: "2026-06-18T23:59:19.028Z"
last_activity: 2026-06-19 -- Phase 07 Plan 02 complete
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 7
  completed_plans: 7
  percent: 50
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-12)

**Core value:** A sarcastic, personality-driven music + AI Discord bot that runs reliably 24/7 — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.
**Current focus:** Phase 07 — player-ux-filters

## Current Position

Phase: 07 (player-ux-filters) — EXECUTING
Plan: 4 of 4
Status: Plan 02 complete — ready for Plan 03
Last activity: 2026-06-19 -- Phase 07 Plan 02 complete

## Accumulated Context

### Decisions

Full decision log lives in PROJECT.md Key Decisions and milestones/v1.0-ROADMAP.md. Highlights:

- Hosting RESOLVED → Oracle Cloud Always Free A1 ARM; Docker Compose for portability (Phase 4)
- Persistence migrated SQLite → PostgreSQL via asyncpg 0.31.0 (Phase 4)
- Queue cap (500) enforced in `MusicQueue.add()`; `log_track_batch` single-transaction logging (Phase 4)
- Gemini-first personality output with guaranteed template fallback; `priority=2` for all background AI (Phase 3)
- [Phase ?]: Mirror /stop template at clear_persisted() gap sites to close ghost-queue-on-restart bug (DEPLOY-06)
- [Phase ?]: DEBUG level for hot per-play _play_track logs, INFO for low-frequency reconnect path
- [Phase ?]: ZoneInfo(config.STREAK_TIMEZONE) for all community-time hour checks; bot.py yt-dlp loop tzinfo deferred (D-06)
- [Phase 05-02]: deploy.sh uses --build bot (not bare --build) — only bot image rebuilt; Postgres never rebuilt
- [Phase 05-02]: pg_restore via docker compose exec (Option B) — version-matched with pg_dump server; avoids host client mismatch
- [Phase 05-02]: build_seed_rows() pure/importable function pattern — separates testable logic from async IO in scripts
- [Phase 05-03]: Strict A→B→C→D runbook ordering — destructive restore (D1) always last; source docs by-reference only, not maintained in parallel
- [Phase 05 review]: 7 of 14 review findings fixed pre-verification (CR-01 restore-loop continue; CR-02 seed-row live-DB teardown; WR-01 backup temp+size-guard; WR-02 deploy dirty-tree/ff-only; WR-05/06 seed-test cleanup; WR-07 /sync owner_id wiring). WR-03 deferred to DEPLOY-04 live debug; WR-04 + 5 Info advisory
- [Phase 05-01]: sanitize_database_url strips entire query string (not per-param) — simpler + safe; SSL handled via ssl='require' kwarg (K-05)
- [Phase 05-01]: DB_POOL_MAX=5, AUDIO_CACHE_MAX_MB=512, DB_MAX_INACTIVE_CONN_LIFETIME=240, DB_STATEMENT_CACHE_SIZE=0 (K-04/K-07)
- [Phase 05-01]: _run_health_server uses asyncio.Event().wait() for cancellable keep-alive on 0.0.0.0:8000 (K-02 amendment)
- [Phase 05-03]: Runbook version 2.0 (Koyeb+Neon) — 22 checks across A(7)/B(3)/C(11)/D(1); verified-live bar is K-17 (all 22 pass on Koyeb+Neon, reported via /gsd-verify-work)
- [Phase ?]: clock-injectable elapsed tracking via now: float | None param — enables pure unit tests without real time.monotonic() calls
- [Phase ?]: _build_ffmpeg_opts is module-level pure function so test_audio.py imports/tests it without mocking AudioService
- [Phase ?]: get_source default path preserved: opus passthrough for no-seek no-filter playback (D-12)
- [Phase 07-02]: NowPlayingView uses timeout=None + stable custom_ids registered in setup_hook (not on_ready) — correct discord.py persistent-view pattern
- [Phase 07-02]: _do_* shared helper pattern — slash command + button both route through one code path, eliminating divergence risk
- [Phase 07-02]: now_playing() derives elapsed from queue.elapsed_seconds() internally — callers don't need to pass it
- [Phase 07]: user_favorites uses count-before/count-after dedupe detection — avoids race window, keeps check atomic with insert
- [Phase 07]: FavoritesView: Select + Queue + Remove 3-widget design — explicit intent selection before queuing or removing prevents accidental queue on remove-intent
- [Phase ?]: user_playlists upsert-exempt cap: count_playlists only blocks genuinely new names
- [Phase ?]: delete_playlist returns bool via asyncpg execute() status string ('DELETE N') — no extra SELECT, avoids race window
- [Phase ?]: list_playlists uses jsonb_array_length(snapshot) for track_count — eliminates a separate COUNT query, keeps metadata atomic
- [Phase ?]: [Phase 07-04]: playlist load idle-start sets current_index to first newly added track before _play_track — mirrors queue_persistence restore pattern

### Pending Todos

None.

### Blockers/Concerns

- [Production risk] Koyeb free WEB service sleep-after-1h requires UptimeRobot keep-alive; K-10 runner swap (HeavenCloud/Wispbyte) is the contingency if pings prove ineffective (K-02 amended).
- [Parked] Live-concurrency reconnect race (`cogs/music.py:~609`) needs a live `/gsd:debug` session — cannot be verified by local boot. Assigned to Phase 5 (DEPLOY-04 / P-01); C11 + C2 runbook checks are the live-observation gate.
- [Human-check pending] User must create Neon project, Koyeb WEB service, UptimeRobot monitor, and run the 05-UAT-RUNBOOK.md end-to-end on live infra before Phase 5 is verified (K-17).

## Deferred Items

Items acknowledged and deferred at v1.0 milestone close on 2026-06-12. All three are live-deploy
verification that the Windows dev machine cannot run — they form the day-1 deployment checklist:

| Category | Item | Status |
|----------|------|--------|
| uat | Phase 04 04-HUMAN-UAT.md — 6 pending live scenarios (Oracle A1 + Postgres + Discord) | superseded by 05-UAT-RUNBOOK.md v2.0 (Koyeb+Neon) |
| verification | Phase 03 03-VERIFICATION.md — 9 live-Discord behavioral checks | carried into 05-UAT-RUNBOOK.md C1-C11 |
| verification | Phase 04 04-VERIFICATION.md — 6 live-deploy checks (Docker/Postgres/cron) | carried into 05-UAT-RUNBOOK.md A/B/D groups |

Carried-forward engineering items (not blockers):

| Category | Item | Status |
|----------|------|--------|
| reliability | Live-concurrency reconnect race (`cogs/music.py:~609`) | Assigned → Phase 5 (DEPLOY-04); C11 runbook check is the live gate |
| reliability | `clear_persisted()` not called on idle-leave / reconnect-failure (IN-02) | Fixed (P-02, Plan 05-01); B2 runbook check is the live gate |
| out-of-scope | Web config dashboard ("maybe" only) | Not committed |

## Session Continuity

Last session: 2026-06-18T23:59:19.021Z
Stopped at: Completed 07-04 user_playlists + /playlist group — 2 tasks (3 commits incl. TDD RED/GREEN), playlists table + save/load/list/delete commands
Next:

  1. User creates Neon project (us-east-2) + Koyeb WEB service (wdc1) + UptimeRobot monitor per `docs/DEPLOY-KOYEB.md`.
  2. User runs `05-UAT-RUNBOOK.md` live on Koyeb+Neon (A→B→C→D order; D1 last).
  3. User reports results via `/gsd-verify-work 05`.
  4. User reviews branch `gsd/phase-5-ship-it-live` and merges → main (user owns the merge).
  5. After merge, update Koyeb tracked branch from `gsd/phase-5-ship-it-live` to `main`.

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| Phase 05-ship-it-live P01 (Koyeb+Neon re-planned) | ~8 min | 2 tasks (3 commits incl. TDD RED) | 3 files (1 created, 2 modified) |
| Phase 05-ship-it-live P02 (deploy packaging) | ~12 min | 2 tasks (2 commits) | 9 files (5 created/moved, 4 modified) |
| Phase 05-ship-it-live P03 (runbook re-target) | ~4 min | 2 tasks (1 commit) | 1 file modified |
| Phase 07-player-ux-filters P01 | 9 min | 5 tasks | 9 files |
| Phase 07-player-ux-filters P02 | ~25 min | 5 tasks (4 commits) | 4 files modified |
| Phase 07 P03 | ~20 min | 2 tasks | 5 files |
| Phase 07-player-ux-filters P04 | ~15 min | 2 tasks | 3 files |
