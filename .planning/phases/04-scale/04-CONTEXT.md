# Phase 4: Scale - Context

**Gathered:** 2026-06-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4 makes Dexter survive as a real, always-on bot across a **handful of servers** with durable, restart-proof persistence. Concretely:

- **Concurrency hardening (SCALE-01):** per-guild queue cap, idle-channel eviction in the message buffer, and batching the per-`/play` DB writes into one transaction.
- **SQLite → PostgreSQL (SCALE-02):** Postgres-only everywhere, started fresh, with all SQLite-specific `datetime('now')`/`AUTOINCREMENT`/`?`-placeholder usage removed.
- **`AutoShardedBot` (SCALE-03):** base-class swap; runs exactly 1 shard at this size (future-proof insurance, not a shard fleet).
- **Queue persistence (SCALE-04):** queue + index + loop mode survive restarts, with smart rejoin on boot.
- **Hosting decision (SCALE-05):** the OPEN question is resolved → Oracle Cloud Always Free, pure-free, Docker Compose, with backup + down-detection so "24/7" is honest.

**Scale is sized for ~5–10 guilds.** This is the anchor: every decision is "make it not fall over and recover cleanly," NOT "prepare for hundreds." The binding ceilings at this size are the free Gemini 15 RPM quota and host CPU/bandwidth — neither of which sharding or Postgres fixes — and at 1–3 concurrent audio streams, neither actually binds.

**Out of scope (clarifies, does not expand):** web config dashboard (PROJECT.md "maybe" only); the live voice-reconnect race at `cogs/music.py:~609` (parked for a dedicated live `/gsd:debug` once running 24/7 — restart-restore here is a *separate, fresh-boot* concern); mid-song playback-position resume; per-guild Gemini rate isolation; genuine multi-shard / hundreds-of-guilds hardening.
</domain>

<decisions>
## Implementation Decisions

### Scale target & limits (the calibrator — drives everything else)
- **D-01:** Target = **~5–10 guilds** ("a few friends' servers"). Future-proofed but lean; do **not** over-engineer for load that won't come.
- **D-02:** **`AutoShardedBot` runs exactly 1 shard** at this size. Implementation = swap `commands.Bot` → `commands.AutoShardedBot` and confirm nothing broke. No manual `shard_count`, no shard fleet — pure future-proof insurance.
- **D-03:** **Gemini limiter stays GLOBAL 15 RPM** with the existing priority tiers. Do NOT split per-guild (15 ÷ 10 ≈ 1.5 RPM each would starve everyone). Priority-2 auto-queue keeps yielding to priority-1 user commands.
- **D-04:** Add a **modest per-guild queue cap** (`MAX_QUEUE_SIZE_PER_GUILD`, ~500–1000) — anti-bloat / anti-abuse, not anti-load. Reject over-cap adds with a personality message. (SCALE-01 "queue caps")
- **D-05:** **Message-buffer idle-channel eviction** — TTL-based cleanup of channels not seen in N hours so the per-channel `_buffers` dict can't grow unbounded across guilds. (SCALE-01 "buffer eviction")
- **D-06:** **DB write-contention fix = batch the 3 sequential commits per `/play`** (`log_song` + `update_artist_count` + `update_user_profile`) into ONE transaction. (SCALE-01 "DB write contention"; note WAL/busy_timeout already shipped in Phase 2.5, so this is the *remaining* fix.)

### Hosting & deployment (SCALE-05 — the resolved OPEN question)
- **D-07:** **Host = Oracle Cloud Always Free, Ampere A1 ARM**, pure-free (**NOT** Pay-As-You-Go). `$0` is a hard priority. Target the larger A1 allocation (~4 OCPU / 24 GB); the AMD `E2.1.Micro` (1 GB) is too small for FFmpeg + Postgres + Python and is only an emergency fallback.
- **D-08:** **Documented fallback host = Hetzner VPS** (~€4–5/mo) if babysitting Oracle gets annoying. This is *why* portability (D-10) matters. (User's running joke nickname for it noted in `<specifics>`.)
- **D-09:** **Oracle reclaim/inactivity hedge = pure-free + keep-alive.** A lightweight periodic CPU/network nudge above Oracle's idle thresholds, implemented as a **cron INDEPENDENT of the bot process** (keeps working even if the bot is briefly down) + periodic console logins to dodge the 30-day-inactivity rule. User **declined Pay-As-You-Go** and accepts residual A1-capacity-crunch risk.
- **D-10:** **Packaging = Docker Compose** (bot + Postgres as containers). One `docker compose up` rebuilds the **entire stack** on any host — fresh Oracle VM after a reclaim, or Hetzner later. Persistent Docker **volumes** for: Postgres data, audio cache (`data/cache/`), logs. Use **arm64** images throughout (python / postgres / ffmpeg / yt-dlp all support ARM).
- **D-11:** **Postgres = LOCAL colocated container** on the same VM (free) — not a managed external service.

### Reliability: backup & down-detection (emergent from the pure-free-Oracle + start-fresh choices)
- **D-12:** **Postgres backup = periodic `pg_dump` → Oracle Object Storage** (Always Free 20 GB). Survives instance reclaim (object storage outlives the compute instance); same-account credentials = simplest. Accepts that a *full account termination* would also take it (residual risk, consistent with D-07/D-09). Rationale: the DB holds the irreplaceable "roast fuel" (streaks, play counts, history) and is tiny, so backup is near-free.
- **D-13:** **Down-detection = dead-man's switch** (e.g. Healthchecks.io free tier). **The keep-alive cron (D-09) pings the check-in URL each beat**; if pings stop, the service alerts (Discord/email/push). This **unifies keep-alive + down-detection into one cron** — no inbound HTTP port, no Oracle ingress rules to manage.

### PostgreSQL migration (SCALE-02)
- **D-14:** **Start FRESH** — no SQLite→Postgres data migration. Dex has only ever been booted locally (no real production history/streaks to preserve), so there is no export/import code and no dialect-conversion of existing rows.
- **D-15:** **Postgres-ONLY everywhere** (prod *and* local dev). Rip out `aiosqlite` entirely; single dialect; dev/prod parity by running the same compose Postgres locally. **No** SQLite-dev / PG-prod dual abstraction.
- **D-16:** **Remove SQLite-isms:** `INTEGER PRIMARY KEY AUTOINCREMENT` → identity/serial; `BOOLEAN DEFAULT 0` → `DEFAULT false`; `TEXT DEFAULT (datetime('now'))` → `timestamptz DEFAULT now()`; `date(col) = date('now')` → `col::date = CURRENT_DATE` (tz-aware where the streak/daily logic requires); `?` placeholders → the chosen driver's style. The streak columns go **straight into the fresh `CREATE TABLE`**, so `migrate_add_streak_columns` (PRAGMA-based) is **deleted**.
- **D-17:** The pure helpers **`get_local_date` / `compute_streak`** (`database.py`) are DB-agnostic and already tz-aware — they **carry over unchanged**. Phase 3's `STREAK_TIMEZONE` boundary work ports cleanly (it was deliberately built Python-side, not in SQL).

### Queue persistence (SCALE-04)
- **D-18:** Persist **queue + `current_index` + `loop_mode`**, per-guild, to a Postgres table. Depth stops there — the currently-playing song **replays from its START** on restore (no mid-song position resume).
- **D-19:** Write on every queue **MUTATION** (add / skip / advance / shuffle / clear / loop-change), **not** just on graceful shutdown — an Oracle reclaim or crash never fires a shutdown hook, which is the exact scenario this protects against.
- **D-20:** Persist the IDs needed to restore context: **`_text_channel_id` AND the voice-channel id**. The voice-channel id is **not on the `MusicQueue` model today** — capture it from `guild.voice_client.channel` at save time.
- **D-21:** Restore on boot = **SMART REJOIN.** If the previously-active voice channel still has humans → rejoin + resume (current song from start). If empty → restore the queue into memory **silently** and wait for the next `/play` or `/resume`. Never blast audio into an empty channel.
- **D-22:** **Boundary:** this restart-restore is **distinct from** the parked live voice-reconnect race (`cogs/music.py:~609`, a mid-session bug). Do not conflate them; the parked bug stays parked.

### Claude's Discretion
- Exact config values: `MAX_QUEUE_SIZE_PER_GUILD`, buffer-eviction TTL, keep-alive interval/method, `pg_dump` cadence, dead-man ping interval, Postgres connection-pool size (planner sets in `config.py`, consistent with existing constants).
- **Async Postgres driver** (asyncpg vs psycopg3) and connection-pool wiring — researcher/planner call.
- **Schema creation / migration tooling** (raw SQL init script vs a migration lib) — planner call. Start-fresh means this can be minimal.
- **Queue-persistence storage shape:** a `guild_queues` table keyed by `guild_id` with a `jsonb` payload (tracks list + index + loop + channel ids) is the natural fit since `Track` is a clean serializable dataclass; planner decides `jsonb`-blob vs normalized rows.
- Keep-alive *mechanism* (synthetic CPU vs outbound network) — but it MUST double as the dead-man ping (D-13).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements / project decisions
- `.planning/ROADMAP.md` §"Phase 4: Scale" — goal + 4 success criteria + the "Out of committed scope" note.
- `.planning/REQUIREMENTS.md` — **SCALE-01…05** (the testable requirement statements).
- `.planning/PROJECT.md` — Key Decisions (hosting OPEN→resolved here; SQLite→PG deferred here; `current_index` queue; global Gemini limiter), Constraints (hosting/AI/music limits), and Out of Scope (web dashboard, live-reconnect race, deferred contention work).

### Build spec
- `CLAUDE.md` — **Database Schema** (the 6 tables being retyped for Postgres), **Configuration** (where new `config.py` settings go), **Discord Intents Required**, **Background Tasks** (existing loop registry), **Build Phases §Phase 4**, **Critical Rules** (esp. #3 FFmpeg cleanup, #10 cache cleanup), **Implementation Gotchas**.

### Codebase maps (current built state)
- `.planning/codebase/CONCERNS.md` — **Scaling Limits** (SQLite bottleneck, in-memory queue, message-buffer growth, 15 RPM), **Missing Critical Features** (No Queue Persistence). NOTE: dated 2026-06-01, *before* Phase 2.5 — WAL, FFmpeg cleanup, yt-dlp self-heal, bare-except, playlist-error, integer-coercion are **already fixed**; do not re-propose them.
- `.planning/codebase/STACK.md` — current `aiosqlite` stack, `.env`/`config.py` model, async architecture, the (now-superseded) "Oracle Cloud free tier" production note.
- `.planning/codebase/{ARCHITECTURE,STRUCTURE,CONVENTIONS,INTEGRATIONS,TESTING}.md` — layered cog→service→model architecture, file layout, conventions, integration wiring, and the testing convention (pure logic = TDD; Discord/process = structural review + clean boot).

### Code integration targets (read before modifying)
- `database.py` — **full rewrite target** (aiosqlite→Postgres). `SCHEMA_SQL`, all `await db.commit()` helpers, `init_db` PRAGMAs (removed), `migrate_add_streak_columns` (deleted), `get_local_date`/`compute_streak` (unchanged). `ON CONFLICT` upserts already used — they port to Postgres nearly verbatim.
- `models/queue.py` — `MusicQueue` (`current_index`, `loop_mode`, `_text_channel_id`, `clear()`), `Track` dataclass (serializable). Add (de)serialization + voice-channel-id capture for persistence.
- `bot.py` — `commands.Bot(...)` → `AutoShardedBot`; aiosqlite connection setup → Postgres pool; `on_ready` queue-restore hook; existing `@tasks.loop` background-task pattern (model for any in-process loop).
- `config.py` — single-file constants + `.env` secrets; add Postgres DSN / `DATABASE_URL`, `MAX_QUEUE_SIZE_PER_GUILD`, buffer TTL, `HEALTHCHECK_URL`, keep-alive interval, etc.
- `cogs/music.py` — queue-mutation call sites (persist-on-mutation hooks), queue-cap enforcement on add, voice-channel-id capture, the parked reconnect race at `~609` (leave alone).
- `models/message_buffer.py` — add idle-channel TTL eviction.
- `services/gemini.py` — global 15 RPM limiter stays as-is (confirm, don't per-guild it).

### Prior context
- `.planning/phases/03-alive/03-CONTEXT.md` — `STREAK_TIMEZONE` decision (D-17 there) and the explicit note that `datetime('now')` is UTC and streak math must use the configured tz; confirms the streak helpers are already Python-side.

### New infra files (to be created this phase — do not exist yet)
- `docker-compose.yml`, `Dockerfile` (arm64) — bot + Postgres + volumes.
- Backup script (`pg_dump` → Oracle Object Storage) and keep-alive/dead-man-ping script/cron.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`get_local_date` / `compute_streak`** (`database.py`) — DB-agnostic, tz-aware pure helpers; carry over **unchanged** through the Postgres migration (TDD-covered seam).
- **`Track` dataclass** (`models/queue.py`) — clean fields (`video_id, title, artist, url, duration_seconds, requested_by, was_auto_queued, thumbnail`); trivially serializable to JSON/`jsonb` for queue persistence.
- **`MusicQueue`** — already centralizes `current_index` + `loop_mode`; `clear()` resets play state (persistence must write-clear on `clear()`). Note: it does **not** hold the voice-channel id — that must be captured separately (D-20).
- **`ON CONFLICT … DO UPDATE` upserts** — already used in `update_artist_count`, `update_user_profile`, `increment_daily_stat`; Postgres supports these identically, so they port almost verbatim.
- **`ERROR_LOG_CHANNEL_ID` / `config.py` env pattern** — template for the new infra env vars (Postgres DSN, `HEALTHCHECK_URL`).
- **`@tasks.loop` background pattern** in `bot.py` (idle check, cache cleanup, status rotation, yt-dlp 04:00 update) — model for any in-process loop (though D-09 prefers the keep-alive be an *external* cron).

### Established Patterns
- Layered **cog → service → model**; services wired in `bot.py` `on_ready`, accessed via `self.bot.<svc>`. A thin **persistence service** (called by `cogs/music.py` on mutations) keeps `MusicQueue` pure rather than wiring DB into the model.
- **Testing convention:** pure logic → TDD in `tests/`; Discord/process code → structural review + clean boot. So the DB-helper rewrite and queue (de)serialization are **TDD candidates**; the `AutoShardedBot` swap, voice rejoin, and Docker/infra are **boot/structural-review**.
- **`config.py`** single-file constants + `.env` secrets — only add settings as the feature is implemented.
- Per-call `await db.commit()` is the current style — **batch into transactions** for the per-`/play` writes (D-06).

### Integration Points
- **`database.py`:** every helper signature changes (`db: aiosqlite.Connection` → pooled Postgres conn/pool). `init_db` loses the PRAGMAs; `migrate_add_streak_columns` is deleted; `SCHEMA_SQL` retyped; `date('now')`/`datetime('now')` replaced.
- **`bot.py`:** base-class swap; pool creation replaces `aiosqlite.connect`; `on_ready` gains the smart-rejoin restore (D-21).
- **`models/queue.py` + `cogs/music.py`:** add `to_dict`/`from_dict` (or equivalent) + persist-on-mutation hooks at every mutation site; capture `voice_client.channel.id` at save; enforce the queue cap on `add`.
- **`models/message_buffer.py`:** add TTL eviction of idle channels.
- **New:** `docker-compose.yml` / `Dockerfile` (arm64, volumes); backup + keep-alive/dead-man scripts.
</code_context>

<specifics>
## Specific Ideas

- **`$0/mo` is a hard constraint.** Every infra choice preserves it: pure-free Oracle (D-07), Oracle Object Storage backup (D-12, within the free 20 GB), Healthchecks.io free tier (D-13). The moment "free" costs reliability the user is annoyed by, the **Hetzner** escape hatch (D-08) opens — and Pay-As-You-Go becomes the natural reclaim-immunity upgrade (see Deferred).
- **The keep-alive cron is intentionally TRIPLE-duty:** (1) nudges Oracle's idle thresholds to avoid reclaim, (2) pings the dead-man's switch for down-detection. Design it as **one** mechanism, external to the bot process.
- **The Postgres data is "roast fuel"** — streaks, play counts, history are what make Dexter's roasts land. Important enough to back up (D-12), not important enough to pay for (start-fresh + Object-Storage-only accepted).
- **"heinrich himmler vps"** — the user's playful nickname for the **Hetzner** fallback host (D-08). Just Hetzner.
</specifics>

<deferred>
## Deferred Ideas

- **Mid-song position resume on restart** — overlaps the parked position-save-on-disconnect work; rejected at restart frequency (D-18). Revisit if restarts ever become frequent enough to annoy.
- **Pay-As-You-Go Oracle upgrade** — the clean reclaim-immunity hedge ($0 within free limits, just a card on file). Rejected now in favor of pure-free + keep-alive; the obvious next move if pure-free babysitting gets annoying (companion to the Hetzner jump).
- **Per-guild Gemini rate isolation** — only matters at hundreds+ guilds; rejected for ~5–10 (would starve everyone). Revisit only if scale target grows.
- **Off-provider backup** (Backblaze B2 / private repo) — more durable than Oracle Object Storage against full *account* termination; rejected for same-account simplicity now.
- **Active HTTP health endpoint + UptimeRobot** — rejected in favor of the dead-man's switch (no inbound port / ingress rules).
- **Persisting `auto_lyrics` / `lyrics_thread_id` across restart** — currently deliberately resets on restart (Phase 3 design); outside the queue+index+loop persistence scope. Could be folded in later for consistency.
- **Web config dashboard** — PROJECT.md "maybe" only; not committed scope.
- **Live voice-reconnect race** (`cogs/music.py:~609`) — stays parked for a dedicated live `/gsd:debug` once running 24/7; cannot be verified by local boot.

*All other discussion stayed within phase scope.*
</deferred>

---

*Phase: 4-scale*
*Context gathered: 2026-06-12*
