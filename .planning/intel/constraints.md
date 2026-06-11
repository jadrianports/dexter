# Constraints (SPEC Intel)

> Source type: SPEC. One entry per constraint. type ∈ {api-contract | schema | nfr | protocol}.
> Precedence: SPEC outranks DOC. None of these SPECs are locked; per-doc precedence override is null on all.

---

## Phase 1 — Music MVP design constraints

source: docs/superpowers/specs/2026-04-12-dexter-phase1-design.md

### C-P1-ARCH — Layered architecture + service wiring
type: protocol
- Layered cog → service → model design. Services initialized in `bot.py`, attached as bot attributes (`bot.youtube_service`, `bot.audio_service`); cogs access via `self.bot`.
- "Grow into the spec": only create files each phase uses. CLAUDE.md structure is the north star.
- Pure `app_commands` slash commands only — no prefix, no hybrid. Guild sync in dev, owner `/sync` in prod.
- First-run sync: `bot.py --first-run [--guild <ID>]` syncs then exits; subsequent boots use `/sync`.

### C-P1-SCHEMA — Phase 1 SQLite schema
type: schema
- Tables: `user_profiles`, `song_history` (+ indexes `idx_history_guild`, `idx_history_user`), `user_artist_counts`, `bot_daily_stats`.
- `image_generation_log` is NOT created in Phase 1 (added with `/imagine` in Phase 2).
- `user_artist_counts` denormalized for fast top-N artist queries. `datetime('now')` is SQLite-specific; acceptable through Phase 3.
- Query helpers exposed by `database.py` (no raw SQL in cogs): `log_song`, `update_artist_count`, `update_user_profile`, `increment_daily_stat`, `get_db`.

### C-P1-AUDIO — Audio format + cache strategy
type: protocol
- Cached files → `FFmpegOpusAudio` (opus passthrough, low CPU). Stream fallback → `FFmpegPCMAudio`.
- No `/volume` command, no `PCMVolumeTransformer` (Discord per-user volume slider covers it).
- Cache: `data/cache/{video_id}.opus`; max `AUDIO_CACHE_MAX_MB` = 2048; evict by oldest last-access; hourly cleanup task.
- `get_source(track)`: cache hit → opus passthrough; miss → download (`DOWNLOAD_TIMEOUT_SECONDS`=10) → stream fallback.

### C-P1-QUEUE — Queue model semantics
type: protocol
- `MusicQueue` uses `current_index` (no popping) to enable `/replay`, `/previous`, loop wrap, future `/history`.
- `Track.url` is the permanent YouTube URL, never a stream URL (stream URLs expire; resolved at play time).
- Skip ALWAYS advances regardless of loop mode; `LoopMode.SINGLE` re-triggers only on natural end (FFmpeg `after` callback). Shuffle only shuffles tracks after `current_index`.

### C-P1-NFR — Phase 1 limits, edge cases, logging
type: nfr
- `MAX_SONG_DURATION_SECONDS`=900 (reject longer); reject livestreams (`duration is None`).
- `MAX_PLAYLIST_IMPORT`=50 (truncate + inform). `IDLE_TIMEOUT_SECONDS`=600 auto-leave. yt-dlp fail → retry once → stream fallback → error.
- Explicit `voice_client.cleanup()` on skip/stop/error/leave to avoid FFmpeg orphans.
- File logging only in Phase 1 (`utils/logger.py`, daily rotation, `LOG_RETENTION_DAYS`=14). Discord error channel deferred to Phase 2.
- yt-dlp gotcha: `extract_flat: True` only for playlist extraction, never for search; use `webpage_url` not `url` for search results.

### C-P1-DEFER — Cross-phase deferrals declared in Phase 1
type: nfr
- `google-genai` SDK (not deprecated `google-generativeai`) for AI, starting Phase 2.
- Image gen: `gemini-2.5-flash-image` with `response_modalities=['IMAGE']` (Phase 2). [RESOLVED 2026-06-11 — authoritative image-gen model is `gemini-2.5-flash-image`, matching shipped `config.py:36`. See INGEST-CONFLICTS.md.]
- Lyrics via `lyricsgenius` (Phase 3). Deployment to Oracle Cloud deferred to Phase 4.

---

## Phase 2 — Personality + AI design constraints

source: docs/superpowers/specs/2026-04-13-dexter-phase2-design.md

### C-P2-GEMINI — Gemini service + rate limiter contract
type: api-contract
- `services/gemini.py` thin wrapper over `google-genai`. Public methods: `chat(system_prompt, conversation, priority=1) -> str` (truncate to `MAX_AI_RESPONSE_LENGTH`=500), `generate_image(prompt, priority=1) -> bytes | None`.
- Typed exceptions: `GeminiRateLimitError`, `GeminiAPIError`, `GeminiRefusalError`.
- Rate limiter `_RateLimiter`: sliding window, `deque` of timestamps, max 15 (`GEMINI_RPM_LIMIT`). `acquire(priority)` — priority 1 = user commands (wait up to 60s), priority 2 = auto-queue/background (raise if wait > 10s). `asyncio.Lock` guards concurrent acquire.
- SDK conversation format is `{"role": "user"|"model", "parts": [{"text": ...}]}` (NOT OpenAI `content` shape).

### C-P2-MODEL — AI/image model + config additions
type: nfr
- `GEMINI_MODEL` = "gemini-2.0-flash"; `GEMINI_RPM_LIMIT` = 15; `MAX_AI_RESPONSE_LENGTH` = 500.
- Image generation: authoritative model `gemini-2.5-flash-image` (RESOLVED 2026-06-11; this SPEC left it generic as "Imagen 3 via the Gemini API", and the Phase 2 plan's `imagen-3.0-generate-002` is superseded — shipped `config.py:36` confirms `gemini-2.5-flash-image`). [See INGEST-CONFLICTS.md.]
- `MAX_IMAGES_PER_USER_PER_DAY`=10; mood thresholds 15/30/50; `AUTO_QUEUE_MAX_ROUNDS`=3, `AUTO_QUEUE_SONGS_PER_ROUND`=3; `ERROR_LOG_CHANNEL_ID` from env (or None).

### C-P2-AUTOQUEUE — Auto-queue protocol
type: protocol
- Triggered by `music.py _on_track_end()` when `advance()` returns None, before `is_playing=False`. Conditions: humans in voice AND `auto_queue_rounds < 3`.
- Flow: last 10 songs → recommendation prompt → `chat(prompt, [], priority=2)` → parse JSON (strip fences, `json.loads`) → 3 suggestions → YouTube search → Track with `was_auto_queued=True`. JSON parse failure: log + personality message + idle timeout. Cap reached: cap message, stop.
- `auto_queue_rounds` resets to 0 when any human uses `/play`. `auto_queue_results` (in-memory) tracks skip rate for "ignored" memory.

### C-P2-DB — Phase 2 DB query helpers (no new tables)
type: api-contract
- `mark_song_skipped(db, guild_id, url)`, `get_recent_songs(db, guild_id, limit=10)`, `get_images_today(db, user_id)`, `get_daily_command_count(db)`.
- Known epiphany: `song_history.was_skipped` exists but Phase 1 never writes it; Phase 2 `/skip` must call `mark_song_skipped` for auto-queued tracks.

### C-P2-INFRA — Cooldowns, error log channel, events cog
type: protocol
- Global cooldown handler `@bot.tree.error` → personality message for `CommandOnCooldown` (no per-command cooldown code).
- `utils/logger.py log_to_discord(bot, embed)`; reads `ERROR_LOG_CHANNEL_ID`; silently skips if unset. Called from Gemini errors, yt-dlp failures, unhandled exceptions.
- `cogs/events.py` Phase 2 minimal: `on_message` feeds `message_buffer` (skip bot authors). Cross-cog auto-queue trigger via `bot.cogs.get("AICog")`; silently skip if AI cog not loaded (no Gemini key).

---

## Phase 2.5 — Hardening pass design constraints

source: docs/superpowers/specs/2026-06-02-dexter-phase2.5-hardening-design.md

### C-P25-SCOPE — Hardening scope discipline (NFR)
type: nfr
- "Production-honest" reliability pass over Phase 1+2. Constraint: bot has been booted locally only — every fix must be reproducible/verifiable by inspection + local boot. Bugs that only manifest under live concurrency are explicitly PARKED, not fixed blind.
- No new architecture; surgical changes preserving the layered pattern. Pure-logic changes get TDD; Discord/process code gets structural review + local boot (consistent with cogs/`bot.py` being untested-by-design per TESTING.md).
- PARKED: reconnect race (`cogs/music.py:~609`, needs live voice), DB write contention (Phase 4), queue caps / buffer eviction (Phase 4), prompt/log sanitization + `.env` gitignore audit (optional hygiene pass).

### C-P25-OBS — Observability (keystone)
type: protocol
- Unsilence bare `except Exception` handlers (`cogs/music.py:53,221,376` and `services/audio.py`): replace with narrowest expected exception type + `log.exception(...)`; surface error embed where user-facing.
- Rationale: `@bot.tree.error` → `log_to_discord` already exists; silent passes are why failures never reach it. Reuse existing logging, do not rebuild plumbing.

### C-P25-FIX — Deterministic + structural fixes
type: protocol
- Playlist import failure → always send `interaction.followup` error embed (no silent fall-through to single-video path).
- First-run cog-load guard: mirror `on_ready` `GEMINI_API_KEY` check in `first_run()` before loading AI cogs.
- Robust auto-queue JSON parse: tolerate fences/prose/object-wrapped array, validate `{title, artist}` shape, log raw on failure; extract to a pure testable function.
- SQLite `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout` in `init_db`. Fix `get_recent_songs` to bind `LIMIT` as int (was `str(limit)`).
- FFmpeg orphan cleanup: try/finally with explicit `source.cleanup()` if playback never starts / client not connected.
- yt-dlp self-heal: daily `@tasks.loop` `pip install -U yt-dlp` (04:00) + on-download-failure update→retry (throttled ≤ once/hour)→stream fallback→error. Implements CLAUDE.md Critical Rule #4.

### C-P25-TEST — Testing + sequencing constraint
type: nfr
- Unit-test pure logic (auto-queue parse, WAL, limit-as-int, yt-dlp retry/fallback, first-run guard where extractable). Structural review + local boot for unsilenced excepts, playlist followup, FFmpeg cleanup.
- Regression gate: full suite green + clean boot after each stage; no new silent failures in `dexter.log`.
- Sequencing: Stage 0 env → #1 unsilence → #5/#6 DB → #2/#3/#4 deterministic → #7/#8 structural → verify.
