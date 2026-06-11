# Milestones: Dexter ("Dex")

A historical record of shipped versions. Newest first.

---

## v1.0 — MVP

**Shipped:** 2026-06-12
**Phases:** 5 (1, 2, 2.5, 3, 4) · **GSD-tracked plans:** 11 (Phases 3–4) · Phases 1–2.5 shipped pre-GSD

**Delivered:** The complete first release of Dexter — a sarcastic, personality-driven Discord bot that plays YouTube music, chats and generates images via Gemini, comes alive with unprompted roasts/reactions/lyrics/history, and is hardened + scaled to run 24/7 on PostgreSQL behind an `AutoShardedBot` on Oracle Cloud A1.

### Stats

- **Timeline:** 2026-04-17 → 2026-06-12 (~8 weeks)
- **Commits:** 71
- **Code:** ~7,139 Python LOC across 49 modules
- **Tests:** 20 test files (251+ passing unit/structural tests at Phase 3; 130 pure + 18 Postgres-integration collected at Phase 4)
- **Git range:** `2c5a95d` (Initial commit) → `912b725` (Merge Phase 4)

### Key Accomplishments

1. **Music engine** — `/play` (search + URL + playlist), full transport controls, `current_index` queue with generation-counter race prevention, cache-first opus audio with stream fallback and 2GB atime eviction, 10-min idle auto-leave. (Phase 1)
2. **Gemini personality + AI** — `/ask` with 10-message context + taste injection + mood/seasonal awareness, `/imagine` (`gemini-2.5-flash-image`, 10/day cap), self-feeding auto-queue with "ignored" memory, and one global 15 RPM priority-tiered rate limiter. (Phase 2)
3. **Production-honest hardening** — unsilenced exception handlers, WAL + `busy_timeout`, robust `parse_suggestions` JSON parsing, FFmpeg orphan cleanup, and a self-healing yt-dlp update→retry→stream→error chain. (Phase 2.5)
4. **"Alive" layer** — Gemini-first unprompted voice/late-night/repeat-song roasts with template fallback, message reactions, expanded seasonal branches, 5-min status rotation, startup + idle-loneliness messages, consecutive-day streaks + song milestones, and `/lyrics` (Genius→AZLyrics, paginated) + `/history`. (Phase 3)
5. **Scale pass** — SQLite→PostgreSQL (asyncpg) migration with single-transaction batched logging, `QueueFullError` cap (500), message-buffer TTL eviction, `AutoShardedBot`, queue persistence across restarts with smart-rejoin. (Phase 4)
6. **Hosting resolved + packaged** — Oracle Cloud Always Free A1 ARM decision, Docker Compose stack (arm64, healthcheck-gated, named volumes), keepalive/dead-man cron + `pg_dump` Object Storage backup. (Phase 4)

### Quality

- All 45 v1 requirements satisfied (45/45 traceability coverage).
- Phase 3 verified 10/10 must-haves; Phase 4 verified 4/4 must-haves (static/structural).
- All 3 Critical + 2 Warning Phase-4 code-review findings applied and confirmed.

### Known deferred items at close: 3 (see STATE.md Deferred Items)

All three are live-deploy verification that the Windows dev machine cannot run — they form the day-1 deployment checklist, not scope gaps:

- Phase 04 `04-HUMAN-UAT.md` — 6 pending scenarios (Oracle A1 + Postgres + Discord)
- Phase 03 `03-VERIFICATION.md` — `human_needed`, 9 live-Discord behavioral checks
- Phase 04 `04-VERIFICATION.md` — `human_needed`, 6 live-deploy checks

Plus carried-forward engineering items: the parked live-concurrency reconnect race (`cogs/music.py:~609`) for a dedicated live `/gsd:debug` session, and the `clear_persisted()`-on-idle/reconnect inconsistency (IN-02).

**Archived:** `milestones/v1.0-ROADMAP.md`, `milestones/v1.0-REQUIREMENTS.md`
