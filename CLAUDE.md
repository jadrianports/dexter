# CLAUDE.md — Dexter Discord Bot Build Spec

## What This Is

Discord bot named "Dexter" (Dex). Plays music from YouTube, chats via Gemini AI, generates images via Imagen. Has a persistent sarcastic personality that tracks user behavior and roasts them.

This file is the authoritative spec. (`dexter-architecture.md` is a local, untracked scratch
doc — gitignored as of Phase 22; do not rely on it and do not re-add it to the repo.)

---

## Tech Stack (do not deviate)

- **Language:** Python 3.11+
- **Discord:** discord.py ≥2.3 (`AutoShardedBot`) + davey + PyNaCl for voice
- **Music:** yt-dlp + FFmpeg (opus, 192kbps)
- **AI Chat:** Google Gemini API via `google-genai` (free tier, `gemini-2.5-flash`)
- **Image Gen:** `gemini-2.5-flash-image` via the Gemini API (free tier)
- **Vision (multimodal):** `gemini-2.5-flash` native image understanding for cadence-gated image roasts (Phase 17 — shares the 15 RPM chat budget at priority 2, NOT the embed limiter; explicit `safety_settings` on every user-content Gemini call)
- **Long-term memory (RAG):** `pgvector` on the same Neon Postgres + `gemini-embedding-001` @ 768d on a **separate** 60 RPM limiter (Phase 11 — zero new infra/cost). Phase 13 added a number-free `taste_episode` memory kind (its own salience/decay tier) distilled from listening history
- **Database:** PostgreSQL 16 via `asyncpg` 0.31.0 — migrated from SQLite in Phase 4; `vector` extension enabled in Phase 11
- **Containerization:** Docker + Docker Compose (bot image only; DB is **Neon serverless Postgres**, not a colocated container — the colocated `postgres:16-alpine` service was dropped in Phase 6)
- **Lyrics:** Genius API via `lyricsgenius` (primary), AZLyrics scrape via `beautifulsoup4` (fallback), LRCLIB `/api/search` (third fallback, Phase 12)
- **Hosting:** the 24/7 cloud deploy is **parked** (YouTube blocks datacenter IPs → free cloud non-viable). Dexter runs on-demand via Docker on the user's PC (residential IP) → **Neon serverless Postgres** (Singapore). Code is substrate-agnostic (Dockerfile + `DATABASE_URL`), so the host swap is config-only.

---

## Project Structure

```
dexter/
├── bot.py                         # Entry point, AutoShardedBot init, cogs, background tasks
├── config.py                      # All settings (see Configuration section)
├── database.py                    # PostgreSQL (asyncpg) init, schema, query helpers, streak logic
├── docker-compose.yml             # bot service only (DB = Neon, no colocated Postgres); named volumes
├── Dockerfile                     # bot image build
├── cogs/
│   ├── music.py                   # Music slash commands + /seek /previous /jump /filter /autolyrics /discover (Phases 6/7/14)
│   ├── ai.py                      # /ask, /roast (both RAG-grounded, Phase 15), AI auto-queue logic
│   ├── imagine.py                 # /imagine
│   ├── memory.py                  # Phase 15/16: /memory view|forget|callbacks (self-scoped, ephemeral)
│   ├── help.py                    # /help
│   ├── ops.py                     # /leaderboard, /skips, /stats (Phases 8/12)
│   ├── library.py                 # /favorite(s), /playlist group, /jam group (+ /jam suggest, Phase 14) (Phases 7/12/14)
│   ├── admin.py                   # Phase 19: /setup group (channel|roasts|vision) — manage_guild-gated per-guild config
│   ├── invite.py                  # Phase 22: public /invite (embed + Add-to-Discord button from build_invite_url)
│   ├── ops.py                     # + Phase 20: /guilds owner group (list|silence|unsilence|leave|block|unblock)
│   └── events.py                  # Unprompted roasts, reactions, mood, status, idle, proactive callbacks (P16), vision roasts (P17)
├── logic/                         # Phase 10: pure, mock-free decision logic (TDD seam)
│   ├── playback.py                # TrackEndAction enum + 5 keyword-only playback fns
│   ├── health.py                  # determine_health_status + assemble_degraded_reasons
│   ├── roasts.py                  # decide_ambient_roast + cooldown_elapsed
│   ├── autoqueue.py               # token-set-containment hallucination validator (Phase 12)
│   ├── taste.py                   # Phase 13/14: classify_artist bands + positive-taste selection
│   ├── proactive.py               # Phase 16: should_fire_proactive_callback gate (chance + daily cap)
│   ├── vision.py                  # Phase 17: should_fire_vision_roast gate (chance + per-user cooldown)
│   ├── guild_config.py            # Phase 18/20: decide_ambient_channel (+ silenced) + is_ambient_channel + decide_interaction_allowed + AmbientSurface enum
│   ├── invite.py                  # Phase 22: build_invite_url() — sole OAuth2 URL constructor (only documented `import discord` in logic/)
│   └── skip_stats.py              # /skips rate computation (Phase 12)
├── services/
│   ├── youtube.py                 # yt-dlp: search, download, metadata extraction, resolution cache, self-heal
│   ├── gemini.py                  # Gemini API: chat, music recs, image gen, embed() (RAG) — Phase 20 per-guild usage tagging
│   ├── memory.py                  # Phase 11: RAG long-term memory (recall/remember/dedup/decay); Phase 21 guild_scoped opt-in read path
│   ├── guild_config.py            # Phase 18/20: GuildConfigService — boot-loaded, fail-closed, cache-only per-guild config + blocklist/silence
│   ├── metrics.py                 # Phase 6: PerfMetrics rolling aggregates for /stats
│   ├── lyrics.py                  # Genius + AZLyrics + LRCLIB
│   ├── queue_persistence.py       # Phase 4: persist/restore queues (guild_queues JSONB), smart-rejoin
│   └── audio.py                   # FFmpeg audio source management (opus-copy / filter transcode)
├── models/
│   ├── queue.py                   # Per-server queue (loop, shuffle, 500 cap, _play_generation counter)
│   ├── user_profile.py            # User taste tracking
│   ├── memory.py                  # Phase 11: MemoryFact dataclass
│   ├── server_state.py            # Per-server runtime state
│   └── message_buffer.py          # Rolling 10-message context per channel
├── personality/
│   ├── prompts.py                 # Gemini system prompts (+ memory-context slot)
│   ├── responses.py               # Templated music command responses
│   ├── roasts.py                  # Unprompted roast logic
│   └── seasonal.py                # Date-aware personality
├── utils/
│   ├── embeds.py                  # Discord embed builders
│   ├── formatters.py              # Duration, progress bars, etc.
│   ├── tasks.py                   # Phase 9: make_task — fire-and-forget with failure surfacing
│   └── logger.py                  # File + Discord channel logging
├── scripts/                       # memory_spike.py (Phase 11 RAG numeric-defaults spike), render_demo_gif.py (Phase 23 demo-GIF renderer)
├── tests/                         # pytest suite (pure unit tests + live-DB integration tests + invite/site drift-guards)
├── site/                          # Phase 23: Astro static landing page (feature showcase + Add-to-Discord), GitHub Pages subpath /dexter
├── .github/workflows/             # Phase 18/23: ci.yml (ruff + pytest on pgvector service container), pages.yml (Pages deploy), release.yml (GHCR image on v* tags)
├── data/cache/                    # Audio cache (Postgres data lives in a Docker volume, not here)
├── requirements.txt
├── requirements-dev.txt           # Phase 18: ruff (lint+format), pinned dev tooling
├── pyproject.toml                 # Phase 18: ruff config (single lint+format tool)
├── .env                           # DISCORD_TOKEN, GEMINI_API_KEY, GENIUS_TOKEN, DATABASE_URL, OWNER_ID, …
└── README.md
```

> **Note:** cooldowns are enforced inline at the command layer; there is no `utils/cooldowns.py`.

---

## Database Schema (PostgreSQL)

Defined in `database.py` as `SCHEMA_SQL` (idempotent `CREATE TABLE IF NOT EXISTS`, applied by
`init_db()` over an asyncpg pool). Migrated from SQLite in Phase 4 — Postgres types throughout
(`TIMESTAMPTZ`, `BIGSERIAL`, `BOOLEAN`, `JSONB`, `now()`). Phase 3 added the streak columns;
Phase 4 added the `guild_queues` table for queue persistence; Phase 6 added `resolution_cache`;
Phase 7 added `user_favorites` + `user_playlists`; Phase 8 added `bot_daily_stats.total_errors`;
Phase 11 enabled the `vector` extension + `user_memories`; Phase 12 added `guild_jams`;
Phase 16 added `user_profiles.proactive_opt_out`. (v1.3 added no new tables — the `taste_episode`
memory is just a new `kind` on `user_memories`, per the kind-agnostic MemoryService design.)
Phase 18 added the `guild_config` table — the per-guild configuration seam that replaces the
hardcoded `config.DEXTER_CHANNEL_ID` single-channel assumption. Phase 20 added the `guild_blocklist`
table (D-01) — the owner kill-switch's persistent blacklist, deliberately its OWN table so
Phase 21's guild-data purge (MEM-04) could run as a clean `DELETE ... WHERE guild_id = $1` with
no "except if blocked" carve-out. `guild_config.is_blocked` is now DEAD/superseded — `guild_blocklist`
is the sole authoritative blacklist (D-03); the column stays in place unused (no `DROP COLUMN`,
additive-only DDL precedent). Phase 20 is also the first reader/writer of `guild_config.silenced`
(via `set_silenced`), which Phase 18 shipped unread. Phase 21 spent the Phase 20 D-01 dividend:
`database.purge_guild_data(pool, guild_id=...)` hard-deletes a departed guild's rows from exactly
four tables (`guild_config`, `guild_queues`, `guild_jams`, guild-stamped `user_memories`) in one
transaction, called from `bot.py::on_guild_remove` (single hook, best-effort, never crashes guild
removal). `guild_blocklist` is excluded from that purge by design — it is why Phase 20 gave it its
own table. Phase 21 also narrows the `user_memories` ANN read path: `recall()`/`search_memories()`
optionally add a `(guild_id = $N OR guild_id IS NULL)` clause when a call site opts in via
`guild_scoped=True`, so a third party's memory never travels between servers on ambient/unprompted
surfaces, while the legacy `guild_id IS NULL` corpus (`daily_batch`'s only writer) stays globally
recallable. The write path (`remember()`, dedup, cap-eviction) is untouched — still fully
`user_id`-scoped, deliberately not reopening the Phase 13 CR-01 scar.

```sql
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id            TEXT PRIMARY KEY,
    username           TEXT NOT NULL,
    total_songs_queued INTEGER DEFAULT 0,
    first_seen_at      TIMESTAMPTZ DEFAULT now(),
    last_active_at     TIMESTAMPTZ DEFAULT now(),
    current_streak     INTEGER DEFAULT 0,   -- Phase 3
    longest_streak     INTEGER DEFAULT 0,   -- Phase 3
    last_streak_date   TEXT,                -- Phase 3 (ISO date in STREAK_TIMEZONE)
    proactive_opt_out  BOOLEAN DEFAULT false -- Phase 16 (per-user proactive-callback silence; ALTER-added)
);

CREATE TABLE IF NOT EXISTS song_history (
    id               BIGSERIAL PRIMARY KEY,
    guild_id         TEXT NOT NULL,
    user_id          TEXT NOT NULL,
    title            TEXT NOT NULL,
    artist           TEXT,
    url              TEXT NOT NULL,
    duration_seconds INTEGER,
    queued_at        TIMESTAMPTZ DEFAULT now(),
    was_skipped      BOOLEAN DEFAULT false,
    was_auto_queued  BOOLEAN DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_history_guild ON song_history(guild_id, queued_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_user  ON song_history(user_id,  queued_at DESC);

CREATE TABLE IF NOT EXISTS user_artist_counts (
    user_id    TEXT NOT NULL,
    artist     TEXT NOT NULL,
    play_count INTEGER DEFAULT 1,
    PRIMARY KEY (user_id, artist)
);

CREATE TABLE IF NOT EXISTS image_generation_log (
    id           BIGSERIAL PRIMARY KEY,
    guild_id     TEXT NOT NULL,
    user_id      TEXT NOT NULL,
    prompt       TEXT NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_imagine_user_date ON image_generation_log(user_id, generated_at);

CREATE TABLE IF NOT EXISTS bot_daily_stats (
    date                   TEXT PRIMARY KEY,
    total_commands         INTEGER DEFAULT 0,
    total_songs_played     INTEGER DEFAULT 0,
    total_ai_queries       INTEGER DEFAULT 0,
    total_images_generated INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS guild_queues (    -- Phase 4: queue persistence
    guild_id   TEXT PRIMARY KEY,
    payload    JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Phase 6: resolution cache (skip YouTube re-search on repeat queries; TTL-expired)
CREATE TABLE IF NOT EXISTS resolution_cache (
    query_key  TEXT PRIMARY KEY,
    video_id   TEXT NOT NULL,
    title      TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

-- Phase 7: per-user favorites (25 cap) and named playlist snapshots
CREATE TABLE IF NOT EXISTS user_favorites (
    user_id          TEXT NOT NULL,
    video_id         TEXT NOT NULL,
    title            TEXT NOT NULL,
    artist           TEXT,
    url              TEXT NOT NULL,
    duration_seconds INTEGER,
    thumbnail        TEXT,
    added_at         TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, video_id)
);
CREATE TABLE IF NOT EXISTS user_playlists (
    user_id    TEXT NOT NULL,
    name       TEXT NOT NULL,
    snapshot   JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, name)
);

-- Phase 8: central error counter
ALTER TABLE bot_daily_stats ADD COLUMN IF NOT EXISTS total_errors INTEGER DEFAULT 0;

-- Phase 12: per-server shared "jam" mixtapes (distinct from per-user favorites)
CREATE TABLE IF NOT EXISTS guild_jams (
    guild_id   TEXT NOT NULL,
    name       TEXT NOT NULL,
    snapshot   JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (guild_id, name)
);

-- Phase 11: RAG long-term memory. Requires `CREATE EXTENSION IF NOT EXISTS vector;`
-- (run FIRST in SCHEMA_SQL) + per-connection pgvector codec via create_pool(init=...).
CREATE TABLE IF NOT EXISTS user_memories (
    id               BIGSERIAL PRIMARY KEY,
    user_id          TEXT NOT NULL,
    guild_id         TEXT,
    kind             TEXT,               -- milestone|late_night|repeat_song|auto_queue_ignored|daily_batch|taste_episode (P13)
    fact             TEXT NOT NULL,
    embedding        vector(768) NOT NULL,  -- gemini-embedding-001 @ 768d
    salience         REAL DEFAULT 0,
    hit_count        INTEGER DEFAULT 1,
    created_at       TIMESTAMPTZ DEFAULT now(),
    last_seen_at     TIMESTAMPTZ DEFAULT now(),
    last_surfaced_at TIMESTAMPTZ,
    surface_count    INTEGER DEFAULT 0,
    expires_at       TIMESTAMPTZ         -- daily decay sweep evicts low-salience expired facts
);

-- Phase 16: per-user proactive-callback opt-out (distinct from /memory forget — silences the
-- surface without deleting memories). Upserted via get/set_proactive_opt_out helpers.
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS proactive_opt_out BOOLEAN DEFAULT false;

-- Phase 18: per-guild configuration seam (CONFIG-01). One row per guild (guild_id alone
-- is the PK — unlike guild_jams' composite key, this is a single settings row, not a
-- named collection). silenced/is_blocked shipped with false defaults and NO reader until
-- Phase 20. Seeded idempotently for the home guild via seed_guild_config_if_absent
-- (ON CONFLICT DO NOTHING, never DO UPDATE — D-09). Phase 20 is the first reader/writer
-- of `silenced` (via set_silenced, D-11/D-14); `is_blocked` is now DEAD/superseded —
-- guild_blocklist (below) is the authoritative blacklist (D-03), left in place unused
-- (no DROP COLUMN — additive-only DDL precedent).
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id           TEXT PRIMARY KEY,
    ambient_channel_id TEXT,
    configured         BOOLEAN NOT NULL DEFAULT false,
    silenced           BOOLEAN NOT NULL DEFAULT false,   -- Phase 20 reader/writer (D-11/D-14)
    is_blocked         BOOLEAN NOT NULL DEFAULT false,   -- DEAD — superseded by guild_blocklist (D-03)
    joined_at          TIMESTAMPTZ DEFAULT now(),
    updated_at         TIMESTAMPTZ DEFAULT now()
);
-- Phase 19: independent per-guild ambient/vision roast toggles (ALTER-added, default true).
-- Threaded through the pure/service seam via the required keyword-only AmbientSurface enum so
-- ROAST/PRESENCE vs VISION can be silenced independently.
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS ambient_roasts_enabled BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS vision_roasts_enabled  BOOLEAN NOT NULL DEFAULT true;

-- Phase 20 / D-01: the owner kill-switch's persistent blacklist gets its OWN table,
-- deliberately separate from guild_config, so Phase 21's guild_config purge (MEM-04) can
-- run as a clean DELETE ... WHERE guild_id = $1 with no "except if blocked" carve-out — a
-- kicked abuser's block survives the purge and a re-invite is refused (OWNER-04).
CREATE TABLE IF NOT EXISTS guild_blocklist (
    guild_id   TEXT PRIMARY KEY,
    reason     TEXT,
    blocked_at TIMESTAMPTZ DEFAULT now()
);
```

> **Phase 13 decay note:** `taste_episode` rows use a shorter decay horizon than Phase 11 kinds
> (`MEMORY_DECAY_DAYS_BY_KIND["taste_episode"] = TASTE_DECAY_DAYS = 30` vs the 90-day default)
> and a below-floor salience (0.4) so stale fads age out; `remember()` self-refreshes `expires_at`
> on dedup for short-decay kinds only, leaving all Phase 11 kinds byte-identical (D-05).

---

## Configuration

All in `config.py`. Single file. Phases 2–17 settings are now implemented — the block below shows the Phase 1 core; the full current set follows it. `config.py` is always the authoritative list.

```python
# Paths
BASE_DIR = Path(__file__).resolve().parent
AUDIO_CACHE_DIR = BASE_DIR / "data" / "cache"    # Path object
LOG_DIR = BASE_DIR / "logs"

# Music
MAX_SONG_DURATION_SECONDS = 900       # 15 min
MAX_PLAYLIST_IMPORT = 50
AUDIO_QUALITY = "192"                  # kbps
AUDIO_CACHE_MAX_MB = 512              # 512MB (K-07; was 2048 pre-v1.1)
IDLE_TIMEOUT_SECONDS = 600            # 10 min
DOWNLOAD_TIMEOUT_SECONDS = 10
SEARCH_RESULTS_COUNT = 5

# Logging
LOG_LEVEL = "INFO"
LOG_RETENTION_DAYS = 14

# Cooldowns
PLAY_COOLDOWN_SECONDS = 2
SKIP_COOLDOWN_SECONDS = 2
HELP_COOLDOWN_SECONDS = 5

# Bot
OWNER_ID = int(os.getenv("OWNER_ID") or "0")
```

**Now implemented (Phases 2–4) — `config.py` is the authoritative list:**

```python
# AI (Phase 2)
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_RPM_LIMIT = 15                  # shared across ALL AI features
MAX_AI_RESPONSE_LENGTH = 500
ASK_COOLDOWN_SECONDS = 5

# Image gen (Phase 2)
IMAGEN_MODEL = "gemini-2.5-flash-image"
IMAGINE_COOLDOWN_SECONDS = 30
MAX_IMAGES_PER_USER_PER_DAY = 10

# Mood + auto-queue (Phase 2)
MOOD_NORMAL_THRESHOLD = 15; MOOD_TIRED_THRESHOLD = 30; MOOD_EXHAUSTED_THRESHOLD = 50
AUTO_QUEUE_MAX_ROUNDS = 3; AUTO_QUEUE_SONGS_PER_ROUND = 3

# Personality / roasts / status / lyrics (Phase 3)
DEXTER_CHANNEL_ID, ERROR_LOG_CHANNEL_ID            # from env
STREAK_TIMEZONE = "America/New_York"               # IANA tz for ALL community-time checks
UNPROMPTED_ROAST_CHANCE = 0.30; LATE_NIGHT_ROAST_CHANCE = 0.50; LATE_NIGHT_HOURS = (1, 5)
REPEAT_SONG_ROAST_THRESHOLD = 3
MILESTONE_SONG_THRESHOLDS = [100, 250, 500, 1000]
MILESTONE_STREAK_THRESHOLDS = [7, 14, 30, 60, 100]
STATUS_ROTATION_INTERVAL_SECONDS = 300; IDLE_LONELINESS_THRESHOLD_SECONDS = 1800
LYRICS_PAGE_SIZE = 1500; HISTORY_PAGE_SIZE = 10; HISTORY_FETCH_LIMIT = 50

# Database / scale (Phase 4)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dexter:dexter@localhost:5432/dexter")
DB_POOL_MIN = 2; DB_POOL_MAX = 5
MAX_QUEUE_SIZE_PER_GUILD = 500                     # enforced in MusicQueue.add()
MESSAGE_BUFFER_TTL_HOURS = 24
HEALTHCHECK_URL = os.getenv("HEALTHCHECK_URL", "") # Healthchecks.io dead-man switch

# Neon pool tuning (Phase 5 / K-04)
DB_MAX_INACTIVE_CONN_LIFETIME = 240                # recycle before Neon scale-to-zero
DB_STATEMENT_CACHE_SIZE = 0                        # disable prepared stmts for PgBouncer tx-mode

# Speed & caching (Phase 6)
PREFETCH_TIMEOUT_SECONDS = 45; RES_CACHE_TTL_DAYS = 14; PERF_ROLLING_WINDOW = 50
SPONSORBLOCK_CATEGORIES = frozenset({"sponsor","selfpromo","intro","outro","interaction","music_offtopic"})

# Player UX & filters (Phase 7)
FFMPEG_FILTERS = {"bassboost","nightcore","slowed+reverb","8d"}  # name → -af chain; "off" = passthrough
FAVORITES_MAX_PER_USER = 25; PLAYLISTS_MAX_PER_USER = 25; PLAYLIST_NAME_MAX_LENGTH = 60
SEEK_COOLDOWN_SECONDS = 2; FILTER_COOLDOWN_SECONDS = 5; FAVORITE_COOLDOWN_SECONDS = 2

# Social & ops (Phases 8/12)
LEADERBOARD_TOP_N = 5; ROAST_COOLDOWN_SECONDS = 30
JAMS_PER_GUILD_MAX = 25; SKIP_STATS_MIN_PLAYS = 5; AUTO_QUEUE_SEARCH_CANDIDATES = 3

# Reliability & ops hardening (Phase 9)
HEALTH_STRICT_STATUS = True         # 503 when degraded (strict) vs legacy 200; env-overridable
DB_COMMAND_TIMEOUT_SECONDS = 30; INIT_WATCHDOG_TIMEOUT_SECONDS = 120; SYNC_TIMEOUT_SECONDS = 30
TASK_ERROR_CHANNEL_COOLDOWN_SECONDS = 300          # dedup window per (task_name, exc_type)
YTDLP_RETRY_BACKOFF_SECONDS = 1.0; YTDLP_MAX_QUICK_RETRIES = 2; HEALTH_DB_PROBE_TIMEOUT = 3.0

# RAG long-term memory (Phase 11) — embeddings on a SEPARATE 60 RPM limiter, never the 15 RPM chat budget
EMBEDDING_MODEL = "gemini-embedding-001"; EMBED_DIM = 768; EMBED_RPM_LIMIT = 60
MEMORY_TOP_K = 8; MEMORY_SIMILARITY_FLOOR = 0.70; MEMORY_DEDUP_THRESHOLD = 0.92
MEMORY_INJECT_CAP = 3; MEMORY_MAX_PER_USER = 150; MEMORY_DECAY_DAYS = 90
MEMORY_CALLBACK_CHANCE = 0.35; MEMORY_DISTILL_BATCH_HOUR = 3   # + rerank weights + salience base weights
```

**v1.3 "Taste Brain" (Phases 13–17):**

```python
# Semantic music memory (Phase 13) — taste_episode is a new memory KIND, not a new table
TASTE_DECAY_DAYS = 30                # shorter half-life than MEMORY_DECAY_DAYS=90 (stale-taste guard, D-03)
TASTE_DISTILL_BATCH_HOUR = 5         # distinct UTC slot, clear of 02:30/03:00/04:00 loops (no Neon herd, D-06)
TASTE_LOOKBACK_DAYS = 7; TASTE_BASELINE_DAYS = 90; TASTE_MIN_ACTIVITY_TRACKS = 5
TASTE_OBSESSION_MIN_PLAYS = 5; TASTE_NEW_ARRIVAL_MIN_PLAYS = 3; TASTE_STEADY_MIN_BASELINE = 5
TASTE_BAND_HEAVY_PLAYS = 5; TASTE_BAND_FEW_PLAYS = 2     # qualitative bands — NEVER embed raw counts
MEMORY_DECAY_DAYS_BY_KIND = {"taste_episode": TASTE_DECAY_DAYS}   # Phase 11 kinds fall back to MEMORY_DECAY_DAYS

# Smarter music brain (Phase 14) — read-only over taste substrate + live SQL
AUTO_QUEUE_POSITIVE_TASTE_CAP = 4        # max injected taste_episode facts into auto-queue prompt
DISCOVER_ADJACENT_COUNT = 3              # max /discover adjacent artists surfaced
DISCOVER_COOCCURRENCE_WINDOW_DAYS = 90   # get_artist_cooccurrence recency bound

# RAG reach (Phase 15) — /memory view page budget (repurposed from a row-count to a char budget)
MEMORY_VIEW_PAGE_SIZE = 3800             # chars per /memory view page (RAG-03)

# Proactive callbacks (Phase 16) — additive 3rd ambient cadence, rarer than roasts
PROACTIVE_CALLBACK_CHANCE = 0.10         # strictly < UNPROMPTED_ROAST_CHANCE (0.30) and MEMORY_CALLBACK_CHANCE (0.35)
PROACTIVE_CALLBACK_DAILY_CAP = 1         # additive per-user, per-calendar-day ceiling

# Vision / multimodal roasting (Phase 17) — highest blast-radius surface, gated hard
VISION_ROAST_CHANCE = 0.12               # strictly < both ambient cadences (D-04)
VISION_ROAST_COOLDOWN_SECONDS = 600      # per-user cooldown
MAX_VISION_IMAGE_BYTES = 8 * 1024 * 1024 # 8MB raw — pre-download guard, headroom under Gemini's 20MB inline cap
VISION_SAFETY_THRESHOLD = "BLOCK_MEDIUM_AND_ABOVE"  # real block — vision only
TEXT_SAFETY_THRESHOLD = "BLOCK_ONLY_HIGH"           # permissive-but-explicit — /ask + /imagine + all non-image chat()
```

---

## Slash Commands

### Music
| Command | Args | Cooldown |
|---------|------|----------|
| `/play` | `<query or URL>` | 2s |
| `/skip` | — | 2s |
| `/pause` | — | — |
| `/resume` | — | — |
| `/stop` | — | — |
| `/queue` | — | 2s |
| `/shuffle` | — | 2s |
| `/loop` | `[off\|single\|queue]` | — |
| `/nowplaying` | — | 2s |
| `/replay` | — | 2s |
| `/history` | — | 5s |
| `/lyrics` | — | 10s |
| `/seek` | `<position>` | 2s |
| `/previous` | — | — |
| `/jump` | `<index>` | — |
| `/filter` | `[bassboost\|nightcore\|slowed+reverb\|8d\|off]` | 5s |
| `/autolyrics` | `[on\|off]` | — |
| `/discover` | — (SQL co-occurrence artist adjacency + confirm-to-queue, Phase 14) | — |

> Now-playing embed also carries a persistent 5-button control view (play/pause, skip, loop, shuffle, stop) — Phase 7.

### AI
| Command | Args | Cooldown |
|---------|------|----------|
| `/ask` | `<question>` (RAG-grounded on invoker's recalled memory, Phase 15) | 5s |
| `/roast` | `@user` (RAG-grounded on the **target's** recalled history, Phase 15) | 30s |

### Image
| Command | Args | Cooldown |
|---------|------|----------|
| `/imagine` | `<prompt>` | 30s |

### Library (Phases 7/12)
| Command | Args | Cooldown |
|---------|------|----------|
| `/favorite` | — (save now-playing) | 2s |
| `/favorites` | — (view + queue) | 2s |
| `/playlist save\|load\|list\|delete` | `[name]` | — |
| `/jam save\|add\|load\|list\|delete\|suggest` | `[name]` — `suggest` = validated generative jam additions (Phase 14) | — |

### Memory (Phases 15/16)
| Command | Args | Cooldown |
|---------|------|----------|
| `/memory view` | — (verbatim, ephemeral, paginated view of what Dexter remembers about you) | — |
| `/memory forget` | — (count preview + danger-confirm; hard-deletes rows **and** embeddings — the trust escape hatch) | — |
| `/memory callbacks` | `[on\|off]` (per-user proactive-callback opt-out; distinct from `forget`) | — |

> All `/memory` subcommands are strictly self-scoped — no `target` arg, no way to inspect another user.

### Admin (Phase 19) — `manage_guild`-gated, per-guild
| Command | Args | Cooldown |
|---------|------|----------|
| `/setup channel` | `<#channel>` (designate the ambient/response channel via a native channel picker; send-permission validated at write) | — |
| `/setup roasts` | `[on\|off]` (toggle ambient/voice roasts for this guild) | — |
| `/setup vision` | `[on\|off]` (toggle vision/image roasts for this guild, independently of roasts) | — |

> `/setup` is gated by an inline `manage_guild` check (`default_permissions` is a UI hint only, never the gate — ONBOARD-02). Ambient/unprompted surfaces stay silent in a guild until `/setup channel` runs; core commands work immediately on join.

### Ops (Phases 8/12)
| Command | Args | Cooldown |
|---------|------|----------|
| `/leaderboard` | — (per-guild songs/streaks/skips) | — |
| `/skips` | — (skip-rate analytics) | — |
| `/stats` | — (owner-only) | — |

### Owner control plane (Phase 20) — `is_owner()`-gated
| Command | Args | Cooldown |
|---------|------|----------|
| `/guilds list` | — (every server Dexter is in, sorted by per-guild Gemini usage — RATE-01) | — |
| `/guilds silence\|unsilence` | `<guild_id>` (stay joined but suppress ambient + commands) | — |
| `/guilds leave` | `<guild_id>` (force-leave; teardown mirrors `clear_persisted()`, purges guild data via `on_guild_remove`) | — |
| `/guilds block\|unblock` | `<guild_id> [reason]` (persistent `guild_blocklist`; a blocked re-invite is refused block-check-first) | — |

> Block/silence are enforced at ONE choke point — `DexterCommandTree.interaction_check` for slash commands (owner-bypassed) + the CONFIG-02 ambient resolver's `silenced` early-return for unprompted surfaces (OWNER-05). No per-cog checks.

### Utility
| Command | Args | Cooldown |
|---------|------|----------|
| `/help` | — | 5s |
| `/invite` | — (public; embed + "Add to Discord" link button from `build_invite_url()`, works in DMs — Phase 22) | 5s |

> `/health` is an aiohttp HTTP endpoint on `0.0.0.0:8000` (not a slash command) — returns degraded-503 when MusicCog fails to load (Phases 5/8/9).

---

## Music Pipeline

```
/play <input>
  → If input is URL (starts with http/youtube.com/youtu.be): queue directly
  → If input is text: search YouTube via yt-dlp, return 5 results as Discord select menu
  → User picks song from dropdown
  → Reject if duration > 900s (15 min)
  → Reject if livestream (no duration)
  → Check cache (data/cache/{video_id}.opus)
  → If not cached: download via yt-dlp (timeout 10s, fallback to stream)
  → Add to server queue
  → If nothing playing: start FFmpeg → Discord voice playback
  → Post/update now playing embed (persistent message, edit on song change)
  → Log: song_history, user_artist_counts, user_profiles, bot_daily_stats
```

Playlist URLs (contains "list="): extract up to 50 tracks, queue all.

### Playback Engine Patterns

- **Generation counter:** `queue._play_generation` prevents stale after-callbacks from firing on skip/stop/replay
- **Channel tracking:** `queue._text_channel_id` — bot posts in the command channel, not #general
- **Silent skip:** Unavailable tracks chained through silently, one summary message at the end
- **Async responses:** `/skip` responds immediately, runs playback via `asyncio.create_task()`

---

## AI Pipeline

### /ask
```
/ask <question>
  → Check cooldown
  → Gather: message_buffer (last 10), user_profile summary, mood, seasonal context
  → Build system prompt (see Personality section)
  → defer() interaction (shows "Dexter is thinking...")
  → Send to Gemini
  → Post response in designated channel
  → Add response to message_buffer
  → Increment daily command count
```

### Auto-Queue
```
Queue empties + users still in voice
  → Gather last 10-15 songs from session
  → Send to Gemini with music recommendation prompt (JSON response)
  → Parse 3 suggestions
  → Search YouTube for each, queue top results
  → Mark as was_auto_queued = true
  → Track skip rate for "ignored" memory
```

### /imagine
```
/imagine <prompt>
  → Check cooldown + daily cap
  → defer() interaction
  → Send to Gemini Imagen
  → If refused/empty: personality error message
  → Post image with sarcastic caption
  → Log to image_generation_log
```

---

## Personality

### System Prompt Core Rules
- Sarcastic, dry, self-aware, lowercase energy
- Never uses caps lock or excessive punctuation
- Responses under 500 chars unless question needs more
- One emoji max per message
- Accurate first, sarcastic second
- References user's music history when relevant
- Dials back sarcasm for genuinely serious/emotional questions
- Mood shifts based on daily command count (normal → tired → exhausted → fumes)

### Mood System
Commands 1-15: normal. 15-30: tired, shorter responses. 30-50: exhausted, openly complains. 50+: running on spite, maximum sarcasm.

Tracked in `bot_daily_stats`, resets at midnight. Mood string injected into Gemini system prompt.

### Seasonal Awareness
Check month/day, inject seasonal context into system prompt:
- December: dreads Christmas music
- October: reluctantly tolerates Halloween
- Feb 14: roasts lonely voice channel users
- Jan 1: mocks resolutions
- Apr 1: extra chaotic

---

## Unprompted Behavior

### Voice Events (cogs/events.py)
- **User joins voice:** 30% roast chance, 5-min cooldown per user, personalized from user profile
- **User joins at 1-5am:** 50% time-related roast
- **Last user leaves voice:** bot auto-leaves after 10 min idle, posts farewell
- **Bot moved to different channel:** always complains

### Message Reactions
- YouTube/Spotify link in chat: react 👀
- "goodnight"/"gn": react 🫡
- Bot mentioned without command: react 😐
- User says thanks to bot: respond with deflecting warmth

### Idle Messages
No commands for 30+ min but users in voice: post one lonely message. Not repeated until next activity.

### Repeat Song Detection
Same song 3+ times in one day by same user: 100% roast, always triggers.

### Milestone Roasts
User hits 100/250/500/1000 total songs queued: always triggers.

### Streak Tracking
Consecutive days using the bot. Milestones at 7/14/30/60/100 days.

### "Ignored" Memory
Track skip rate on AI auto-queued songs. Reference outcome next time auto-queue triggers.

### Status Rotation
Every 5 min, rotate from pool: current song, server count, personality lines, seasonal.

### Startup Message
On boot: post "i'm back. did you miss me. probably not." in designated channel.

### Proactive Memory Callbacks (Phase 16)
A third, rarest ambient cadence. On `on_message` in the designated channel, a pure
`should_fire_proactive_callback` gate (chance `0.10` + additive daily cap `1`, both below the
ambient roast cadences) may volunteer a remembered detail — reply-anchored with
`AllowedMentions.none()`, recall anchored on the triggering message so it reads as relevant, not
surveillance. Per-user opt-out via `/memory callbacks off`. Never a cold poll, never a DM.

### Vision / Multimodal Roasts (Phase 17)
Image posted in the designated channel → `should_fire_vision_roast` gate (chance `0.12` + per-user
cooldown, priority-2 on the 15 RPM budget). Oversized/wrong-mime images are rejected **before
download**. A safety-blocked reaction is **silently skipped** (no visible refusal, no fallback
template). Shares the Phase 16 `proactive_opt_out` silence.

---

## Now Playing Embed

Persistent message, edited on song change. If edit fails (rate limit), send new one.

Fields: title, artist, duration, progress bar, requested by, loop mode, lyrics snippet (first verse), "/lyrics for full lyrics" footer, YouTube thumbnail.

---

## Edge Cases

| Case | Handle |
|------|--------|
| Bot disconnect mid-song | Save position, reconnect, resume. 3 attempts then error. |
| Song > 15 min | Reject with personality message |
| Livestream URL | Reject with personality message |
| Voice empty 10 min | Auto-leave, clear queue, post message |
| Same song 3+ times/day | 100% roast, still plays |
| Playlist > 50 songs | Truncate to 50, inform user |
| yt-dlp fails | Auto-update, retry, fallback stream, then error |
| Gemini rate limit (15 RPM) | Global rate limiter, queue requests, personality error |
| Imagen refuses prompt | Personality-flavored refusal |
| FFmpeg orphan process | Explicit cleanup in error handlers |

---

## Logging

### File Logging
Location: `LOG_DIR` = `logs/` (NOT `/var/log/dexter/`), **plus stdout** so Docker/container log viewers capture output (K-16).
- `dexter.log`: INFO+ (commands, songs, queries). Daily rotation, 14-day retention.
- `error.log`: ERROR+ only. Weekly rotation, 30-day retention.

### Discord Error Channel
Private channel, bot posts:
- yt-dlp failures (after retry)
- Gemini errors / rate limits
- Unexpected disconnects
- Unhandled exceptions
- Daily summary embed (commands, songs, errors)

---

## Cache Management

Directory: `data/cache/`
Files: `{video_id}.opus`
Max size: 512MB (`AUDIO_CACHE_MAX_MB`). When exceeded, evict **least-played** tracks (lowest `song_history` play_count — NOT `atime`, which is unreliable on `noatime` mounts), skipping any `protected_video_ids` currently in use. (Phase 6 / K-07; was 2GB-by-atime pre-v1.1.)
Hourly cleanup loop checks total size.

---

## yt-dlp Maintenance

Daily auto-update at 4am: `pip install -U yt-dlp`
On download failure: attempt update → retry → fallback stream → error message.

---

## Background Tasks

Start on bot ready:
1. Status rotation (every 5 min)
2. Idle voice channel check (every 60s)
3. Cache cleanup (every hour) — LFU by `song_history` play count, protects in-use tracks (Phase 6)
4. yt-dlp update check (daily 4am)
5. Daily stats reset (midnight)
6. Memory distill batch (daily 03:00 UTC — background message-buffer → RAG facts, Phase 11)
7. Memory decay sweep (evicts low-salience expired `user_memories`, Phase 11)
8. Taste distill batch (daily 05:00 UTC — `song_history` → number-free `taste_episode` facts; own slot, guild-scoped, Phase 13)

> Fire-and-forget tasks are launched via `utils/tasks.py::make_task` (Phase 9) — a done-callback surfaces exceptions to `dexter.log` + the error channel instead of vanishing silently. Next-track prefetch (`_prefetch_next_track`) is generation-guarded to avoid racing skip/stop teardown (Phase 6).

---

## Discord Intents Required

- `message_content` — reading messages for context buffer
- `voice_states` — detecting voice join/leave for unprompted roasts
- `members` — resolving user info for personalized roasts
- `guilds` — server info

Enable all in Discord Developer Portal.

---

## Environment Variables (.env)

```
DISCORD_TOKEN=
GEMINI_API_KEY=
GENIUS_TOKEN=
DATABASE_URL=            # Neon Postgres DSN (sanitized to strip channel_binding/sslmode)
OWNER_ID=               # owner-only commands (/stats, /sync)
DEXTER_CHANNEL_ID=      # designated ambient/response channel
ERROR_LOG_CHANNEL_ID=   # private error-log channel
HEALTHCHECK_URL=        # optional Healthchecks.io / UptimeRobot dead-man switch
STREAK_TIMEZONE=        # optional IANA tz override (default America/New_York)
HEALTH_STRICT_STATUS=   # optional; "false" reverts /health to legacy 200
```

---

## Build Phases

### Phase 1 — MVP ✅ COMPLETE
1. Project setup: discord.py, yt-dlp, FFmpeg, aiosqlite, davey
2. SQLite schema (all tables)
3. Config file
4. /play with 5-result YouTube search + select menu
5. /skip, /pause, /resume, /stop, /queue
6. Queue model (per-server, loop modes, shuffle)
7. Audio: download-first + stream fallback + cache
8. Now playing embed (persistent, edited on song change)
9. Duration cap + playlist truncation
10. Voice auto-leave on idle
11. Disconnect recovery (reconnect + retry, no position save yet)
12. /help
13. /nowplaying, /replay (moved up from Phase 3)
14. File logging (logs/ dir, daily rotation)
15. Command sync via --first-run --guild CLI flag + /sync owner command

**Deferred to Phase 2/3:** Designated channel support, /history, /lyrics, deploy to a cloud host

### Phase 2 — Personality + AI ✅ COMPLETE
1. /ask with Gemini + 10-message context
2. Full personality system prompt
3. User profile tracking in SQLite
4. User taste summary for Gemini prompt injection
5. Mood system
6. Typing indicator / defer
7. AI auto-queue
8. "Ignored" memory
9. All command cooldowns
10. /imagine with daily cap
11. Discord error log channel

### Phase 3 — Alive ✅ COMPLETE
1. Unprompted voice roasts (join/leave)
2. Roast frequency + cooldowns
3. Late night roasts
4. Repeat song roasts
5. Emoji reactions
6. Seasonal awareness
7. Status rotation
8. Startup message
9. Idle loneliness messages
10. Streak tracking + milestones
11. /lyrics (Genius + AZLyrics + pagination)
12. /history
13. yt-dlp auto-update

### Phase 4 — Scale ✅ COMPLETE
1. Multi-server hardening
2. SQLite → PostgreSQL (asyncpg 0.31.0)
3. AutoShardedBot
4. Queue persistence (`guild_queues` JSONB + smart-rejoin on restart)
5. Docker Compose (`postgres:16-alpine` + bot), healthcheck / keepalive
6. ~~Web config dashboard~~ — dropped (never committed)

### Phase 5 — Ship It Live ✅ CODE COMPLETE (24/7 deploy PARKED)
1. Deploy substrate re-targeted **a first cloud WEB-service attempt → Neon serverless Postgres** (the archived Phase-5 deploy attempt lives under `.planning/`)
2. Neon-tuned asyncpg pool (`ssl='require'`, `statement_cache_size=0`, 240s lifetime), `sanitize_database_url`, aiohttp `/health` on `0.0.0.0:8000`, host-neutral Dockerfile, stdout logging
3. `clear_persisted()` gap closure on idle-leave / reconnect-failure (DEPLOY-06), reconnect-race hardening (DEPLOY-04), TZ-correct late-night roast via `ZoneInfo(STREAK_TIMEZONE)` (D-06)
4. `docs/DEPLOY-DOCKER.md` + a 22-check live-UAT runbook — **24/7 deploy PARKED behind the YouTube datacenter-IP block; bot runs on the user's PC (residential IP) → Neon Singapore on demand**

### Phase 6 — Speed & Caching ✅ COMPLETE
Generation-guarded next-track prefetch (zero inter-song gap), Postgres `resolution_cache` (URL-bypass), 3-PP SponsorBlock→FFmpegExtractAudio→ModifyChapters chain + codec-path logging, download-timeout→stream fallback, LFU cache eviction (protects in-use), `PerfMetrics` in `/stats`.

### Phase 7 — Player UX & Filters ✅ COMPLETE
Persistent 5-button `NowPlayingView`, `/seek` `/previous` `/jump`, four `/filter` presets (opus-passthrough preserved for non-filtered tracks), `user_favorites` + JSONB `user_playlists`.

### Phase 8 — Social & Ops ✅ COMPLETE
`/roast @user` (Gemini-personalized, template fallback, `AllowedMentions.none()`), per-guild `/leaderboard`, owner-only `/stats`, degraded-but-always-200 `/health`, `total_errors` tracking.

### Phase 9 — Reliability & Ops Hardening ✅ COMPLETE
Truthful `/health` (degraded-503, `_ready_done`-guarded), fire-and-forget failure surfacing via `make_task`, un-wedgeable `on_ready` watchdog + `_sync_retry_active`-guarded startup-sync recovery, config-driven DB query timeouts, bounded YouTube search/extract self-heal. *(Live-runtime UAT parked behind the host.)*

### Phase 10 — Critical-Path Test Coverage ✅ COMPLETE
Extracted decision logic into pure `logic/` modules (`playback`, `health`, `roasts`, later `autoqueue`/`skip_stats`) locked by ~83 mock-free unit tests with three named scar regressions; full-suite-green + clean-boot regression gate.

### Phase 11 — RAG Long-Term Memory ✅ COMPLETE
`pgvector` on Neon + `gemini-embedding-001` @ 768d on a separate 60 RPM limiter; full read (recall/rerank/floor) + write (remember/dedup/cap-evict) halves, sensitivity/PII + numbers-from-SQL accuracy firewall, callback roasts at four surfaces, daily decay sweep. **Zero new infra.** *(Live-runtime UAT parked behind the host.)*

### Phase 12 — Richer Music/UX ✅ COMPLETE
Per-server `/jam` shared playlists, `/skips` analytics, LRCLIB third lyrics fallback, token-set auto-queue hallucination validation (`logic/autoqueue.py`).

### Phase 13 — Semantic Music Memory ✅ COMPLETE
New number-free `taste_episode` memory kind (own salience 0.4 + 30-day decay tier via `MEMORY_DECAY_DAYS_BY_KIND`), `song_history` aggregate helpers, D-05 self-refresh-on-dedup (`refresh_memory_expiry`), and a `taste_distill_batch` @tasks.loop @ 05:00 UTC — foundation the rest of v1.3 reads from. Zero new tables (kind-agnostic MemoryService).

### Phase 14 — Smarter Music Brain ✅ COMPLETE
Taste-aware auto-queue (recent skips as negative hint + positive room-taste blend + D-02 hard post-filter), `/discover` (invoker-anchored SQL co-occurrence adjacency, never hallucinated), `/jam suggest` (validated generative jam additions reusing `logic/autoqueue.py`). Read-only over taste substrate + live SQL; `logic/taste.py` pure seam.

### Phase 15 — RAG Reach ✅ COMPLETE
`recall()` grounds `/roast @user` (target-scoped) and `/ask` (D-01 removed the `MEMORY_CALLBACK_CHANCE` gate from these two only; ambient surfaces keep it). New `cogs/memory.py`: `/memory view` (verbatim, ephemeral, char-budget paginated) + `/memory forget` (verified hard-delete of rows **and** embeddings — the trust escape hatch Phase 16 depends on). `list_user_memories` / `delete_all_user_memories` helpers.

### Phase 16 — Proactive Memory Callbacks ✅ COMPLETE
Additive 3rd ambient cadence: pure `logic/proactive.py` gate (`PROACTIVE_CALLBACK_CHANCE=0.10` + `DAILY_CAP=1`, rarer than roasts) volunteers a memory on `on_message` in the designated channel. `user_profiles.proactive_opt_out` column + `/memory callbacks on|off`. Pitfall-1 `pre_recalled_memories` bypass keeps the ambient 0.30/0.35 cadence byte-identical.

### Phase 17 — Vision / Multimodal Roasting ✅ COMPLETE
Cadence-gated (`VISION_ROAST_CHANCE=0.12` + per-user cooldown, priority-2) image roasts via `gemini-2.5-flash` vision; before-download mime/size gate (`MAX_VISION_IMAGE_BYTES=8MB`); safety-block = **silent skip** (never a fallback template); `_build_safety_settings` retrofit across all 3 `generate_content` sites (VIS-03). `logic/vision.py` pure gate; reuses Phase 16 opt-out.

### Phase 18 — Per-Guild Config Foundation & CI Gate ✅ COMPLETE
The hardcoded single-channel assumption is gone. `guild_config` table + pure `logic/guild_config.py` seam + boot-loaded, fail-closed `services/guild_config.py::GuildConfigService` cache (zero per-event Neon round-trips) drive every ambient surface; `_resolve_dexter_channel`/`_get_ambient_channel` deleted, both bare-equality `DEXTER_CHANNEL_ID` gates replaced, the env var demoted to a home-guild bootstrap seed (`ON CONFLICT DO NOTHING`, D-09) and removed from `cogs/` entirely — **an unconfigured guild is structurally silent** (CONFIG-01…05). Ruff adopted as a blocking lint/format gate; `.github/workflows/ci.yml` runs ruff + pytest against a `pgvector/pgvector:pg16` service container on every push/PR with zero secrets (CICD-01).

### Phase 19 — Onboarding & Admin Setup ✅ COMPLETE
Any admin can turn Dexter "on" for their own guild. Two per-guild toggle columns (`ambient_roasts_enabled`, `vision_roasts_enabled`) + a required keyword-only `AmbientSurface` enum threaded through the pure/service seam (a surface must name itself to fire — also closed the CONFIG-04 reaction hole); guild-lifecycle glue (`on_guild_join`/`on_guild_remove`, boot backfill welcoming offline-invited guilds exactly once, home-guild-only startup, owner join/leave notices); new `cogs/admin.py` `/setup` group (channel/roasts/vision) with an inline `manage_guild` gate (ONBOARD-01…05).

### Phase 20 — Owner Control Plane & Rate Observability ✅ COMPLETE
The reactive half of safety, at ONE choke point. Dedicated `guild_blocklist` table (own table — D-01, so Phase 21's purge stays a clean DELETE) + first reader/writer of `guild_config.silenced`; pure `silenced` early-return in `decide_ambient_channel` + `decide_interaction_allowed`; `DexterCommandTree.interaction_check` enforces block/silence for every slash command (owner-bypassed) + `on_guild_join` block-check-first re-invite refusal; `GuildConfigService` extended with an O(1) `_blocked` set + cache-only silence reads + write-then-invalidate setters; TOCTOU pre-send re-checks on the reply-after-Gemini paths; per-guild Gemini usage tagging/counters + a `/guilds` owner group (OWNER-01…06, RATE-01).

### Phase 21 — Memory Scoping & Guild Data Lifecycle ✅ COMPLETE
Hybrid scoping shipped (the Descope Rule's tripwires never fired). `recall()`/`search_memories()` gained an **explicit per-call-site `guild_scoped=True` opt-in** adding a `(guild_id = $N OR guild_id IS NULL)` clause — every unprompted/ambient surface opts in, `/ask` stays deliberately global (MEM-02); the legacy `guild_id IS NULL` corpus stays globally recallable (MEM-03). Write path (dedup, cap-evict) untouched — still `user_id`-scoped (CR-13-01 scar not reopened). `database.purge_guild_data` hard-deletes a departed guild's rows from four tables from `bot.py::on_guild_remove` (best-effort); `guild_blocklist` excluded by design (MEM-01…05).

### Phase 22 — Invite Plumbing ✅ COMPLETE
`logic/invite.py::build_invite_url()` — the sole least-privilege OAuth2 constructor (the one documented `import discord` exception in `logic/`) over `INVITE_PERMISSIONS_VALUE=309240908864` (ten named permissions, negatively asserted free of Administrator/Manage Guild/Manage Roles); public `/invite` (`cogs/invite.py`) returns an embed + "Add to Discord" link button built only from that function, works in DMs, prefers `bot.application_id` so forks emit their own client id; CI drift-guard (`tests/test_invite_drift_guard.py`) fails the build if any tracked doc's invite URL drifts (INVITE-01/02).

### Phase 23 — Portfolio Surface & CI/CD ✅ COMPLETE
The recruiter-facing deliverable. Static Astro `/site` landing page (hero + feature showcase + "Add to Discord" from the same invite source of truth, GitHub Pages subpath `/dexter`); README rewritten as an architecture case study (badges, CI status, working invite link); honest scope-boundary docs (100-guild wall, on-demand hosting, full-savage + reactive-kill-switch tradeoff, hybrid memory scoping — PORT-04); `pages.yml` + `release.yml` (GHCR image on `v*` tags) + a `site_drift_guard` test (PORT-01/03/04). **PORT-02 (demo-GIF Dexter lines), CICD-02 (Pages toggle), CICD-03 (GHCR flip) deferred blocked-on-human** — owner-performed GitHub-UI / live-bot steps (23-HUMAN-UAT.md).

> **Milestone status:** v1.0–v1.4 all shipped (code), archived & tagged — `v1.0`/`v1.1`/`v1.2`/`v1.3`/`v1.4`. **v1.4 "Open House" (Phases 18–23, 32 plans, 78 tasks) closed 2026-07-14** — 28/31 requirements shipped at the code level (3 deferred blocked-on-human: PORT-02, CICD-02, CICD-03), pushed to `origin/main`, CI green against a live pgvector container. The 24/7 live deploy + the Phase 03–06/09/11/14–22 live-Discord UAT tail (36 items) remain **parked** behind an always-on residential host — zero code gaps. Next: `/gsd:new-milestone`. See `.planning/PROJECT.md` + `.planning/STATE.md` for authoritative current state.

---

## Critical Rules

1. **All AI features share 15 RPM Gemini limit — implement global rate limiter**
2. **Always check if input is URL before searching — skip search menu for direct URLs**
3. **Kill FFmpeg processes explicitly on skip/stop/error — prevent orphans**
4. **yt-dlp WILL break — auto-update daily and on failure**
5. **Never sacrifice factual accuracy for personality in /ask responses**
6. **Dial back sarcasm for serious/emotional questions**
7. **One emoji max per message — the bot is too tired for more**
8. **Lowercase everything — the bot does not use caps lock**
9. **Designated channel only — don't spam every channel**
10. **Cache cleanup must run — unchecked cache will fill the host's ephemeral disk (512MB cap, LFU eviction)**
11. **Embeddings use the SEPARATE 60 RPM limiter — never the shared 15 RPM chat budget (RAG memory must not starve `/ask`)**
12. **Memory is roast ammo, not a number source — hard numbers in output come from live SQL, never from embedded facts (accuracy firewall)**
13. **Never embed raw play counts in `taste_episode` facts — distill to qualitative bands (`TASTE_BAND_*`); the accuracy firewall applies to taste memory too (Phase 13)**
14. **Every Gemini call that can receive user-influenced content sets explicit `safety_settings`** — Gemini 2.5 defaults them OFF; vision uses a real block (`BLOCK_MEDIUM_AND_ABOVE`), `/ask`/`/imagine` stay permissive-but-explicit (`BLOCK_ONLY_HIGH`) so edgy output doesn't regress (Phase 17 / VIS-03)
15. **A safety-blocked vision reaction is a SILENT skip — never a visible refusal or the generic rate-limit fallback template (Phase 17 / VIS-02)**
16. **`/memory forget` must be a real hard-delete (rows + embeddings) — it is the trust escape hatch proactive callbacks (Phase 16) hard-depend on shipping first**
17. **Guild-scoping on memory recall is an EXPLICIT per-call-site opt-in (`guild_scoped=True`), never inferred from `guild_id` presence** — `/ask` also passes a real `guild_id` and must stay global (MEM-02); only unprompted/ambient recall (`/roast`, ambient roasts, proactive callbacks, the music-command callback, the auto-queue taste blend) opts in (Phase 21)
18. **Ambient/unprompted surfaces stay silent in a guild until `/setup channel` runs — an unconfigured guild is structurally silent (never a system-channel/first-writable fallback)** — the pre-`/setup` fallback chain would fire roasts/vision at strangers within minutes of an invite, the exact abuse surface the kill-switch only mitigates reactively; core commands (`/play`, `/ask`, …) work immediately on join (Phase 18/19, CONFIG-04)
19. **The block/silence kill-switch is enforced at ONE choke point each — `DexterCommandTree.interaction_check` for slash commands (owner-bypassed) and the CONFIG-02 ambient resolver's `silenced` early-return for unprompted surfaces — never per-cog checks** (Phase 20, OWNER-05); reads are cache-only (no Neon on the hot path) and TOCTOU-safe (re-checked immediately before the final send on reply-after-Gemini paths, OWNER-06)
20. **`guild_blocklist` is its OWN table and is NEVER purged by `purge_guild_data`** — a kicked abuser's block must outlive their guild data so a re-invite is refused; the four-table purge list stays hardcoded SQL literals so it can never sweep the blocklist in (Phase 20 D-01 / Phase 21 MEM-04)

---

## Implementation Gotchas

**Phase 1 (music pipeline):**
- **yt-dlp `extract_flat: True`** breaks search queries — only use for playlist extraction (PLAYLIST_OPTS), never for search (SEARCH_OPTS)
- **yt-dlp search results:** use `entry.get("webpage_url")` not `entry.get("url")` — the latter is a stream URL that expires
- **Never call `voice_client.stop()` before `_play_track()`** — the old after-callback fires before generation increments, causing double-play races. Let `_play_track` handle stopping internally.
- **Slash command interactions must respond within 3s** — `defer()` or respond immediately, then do async work via `asyncio.create_task()`

**Phases 4–5 (Postgres + deploy):**
- **asyncpg multi-statement DDL** only works when there are no `$N` params — `SCHEMA_SQL` is plain DDL applied in one `conn.execute()` (Pitfall 1)
- **`clear_persisted()` must mirror the `/stop` template** at every queue-teardown site (`_play_generation += 1` → `clear()` → `clear_persisted()`) or a ghost queue restores on restart (DEPLOY-06 / IN-02). **Teardown sites include natural queue exhaustion** — when the last track ends with nothing to resume, `current_index` stays parked on the finished track, so without `clear_persisted()` smart-rejoin replays it on the next restart (v1.1 live UAT)
- **Community-time checks use `ZoneInfo(config.STREAK_TIMEZONE)`**, never naive `datetime.now().hour` — the host VM runs UTC, so naive time fires roasts/streaks on the wrong calendar day (D-06 / D-17)
- **`restore_queues` must `continue` per-guild, not `return`** — one guild's failed smart-rejoin must not abort restoration for the rest (CR-01)
- **`pg_restore` runs via `docker compose exec` (version-matched)**, never the host client, to dodge a server/client version mismatch
- **Neon / serverless Postgres:** the asyncpg pool MUST use `statement_cache_size=0` + `ssl='require'` + a bounded `max_inactive_connection_lifetime` (~240s) — prepared statements break through PgBouncer and the pool must survive Neon's scale-to-zero, else SSL-EOF / `channel_binding` crashes (Phase 5 / K-04)

**Phases 6–8 (speed, player UX, social):**
- **Gate playback-start on `voice_client.is_playing()`, never the `queue.is_playing` flag** — `_on_track_end` leaves `is_playing=True` and defers to `try_auto_queue` on natural exhaustion ("auto-queue will handle it"), so a `not queue.is_playing` guard never fires and tracks queue but never play (silent auto-queue; v1.1 live UAT). The voice client is the only ground truth for "audio is flowing".
- **Resolution-cache hits must route through `async_extract`** (full duration/livestream guards), never inline `Track` construction — a stale cached `video_id` would otherwise bypass the validity checks (D-09)
- **Persistent discord.py views:** `timeout=None` + stable `custom_id`s registered in `setup_hook` (NOT `on_ready`) — otherwise buttons stop responding after a restart (Phase 7)
- **opus-copy is the default fast path; transcode ONLY when `active_filter` is set** per-track — don't remove the opus-copy path for non-filtered tracks (PERF-02 / PLAYER-07, D-10/D-12)
- **SponsorBlock PP order** is `SponsorBlock(when=after_filter) → FFmpegExtractAudio → ModifyChapters`; don't hand-write opus-copy — `FFmpegExtractAudioPP` already copies natively, `download()` only adds `postprocessor_hooks` for codec-path logging (D-01)

**Phases 9–12 (reliability, tests, RAG memory, richer UX):**
- **`/health` degraded check is guarded by `_ready_done`** — without it the endpoint reports false-degraded during legitimate startup before MusicCog loads (Pitfall 3). `HEALTH_STRICT_STATUS` env-toggles 503-vs-200 so a deploy can opt out without a code change (D-01)
- **`asyncio.TimeoutError` must be caught BEFORE generic `except Exception`** in `on_ready`/DB handlers — in Python 3.11+ `TimeoutError` is a subclass of `Exception`; asyncpg client-side timeout raises `TimeoutError`, not `QueryCanceledError` (REL-04)
- **`_sync_retry_active` module-level bool** guards against multiple READY shards spawning concurrent sync-retry chains; `first_run` sync failure logs + closes (no running loop to retry into) (Pitfall 5 / REL-03)
- **`_play_track` create_task calls stay bare `asyncio.create_task`** — they handle failures internally; a `make_task` callback there would double-log track errors (Pitfall 4). Use `make_task` only for genuine fire-and-forget (prefetch, auto-queue, auto-lyrics)
- **YouTube self-heal reuses the existing `update_ytdlp()` + `_UPDATE_THROTTLE_SECONDS`** path — no second update path; `_is_transient_ytdlp_error` returns False only for `ExtractorError.expected=True` (conservative: treat unknown errors as transient) (D-08)
- **`logic/` is the pure-logic seam** — Discord/process glue dispatches on the returned enum/verdict (e.g. `TrackEndAction`); do NOT mirror the branch logic back in the caller (D-02). Phase 11's rerank/dedup follow the same clock-injectable, keyword-only, mock-free convention
- **pgvector codec registers per-connection via `create_pool(init=...)`** — a per-connection codec, NOT a prepared statement, so `statement_cache_size=0` is a verified non-issue. `CREATE EXTENSION IF NOT EXISTS vector;` must run FIRST in `SCHEMA_SQL` (extension-first boot)
- **Accuracy firewall (Phase 11):** never embed SQL-known numbers (counts/streaks); the distillation gate strips sensitive/PII content, and hard numbers in a roast come from live SQL — memory supplies the *episode*, SQL supplies the *number* (Critical Rules 5/12)
- **Memory callback cadence gate is per-surface** (`random.random() < MEMORY_CALLBACK_CHANCE`) — an occasional stat×episode payoff, not every roast; `guild_id=''` is safe in `_build_roast_line` because ANN recall scopes to `user_id` only (D-04)
- **`strip_lrc_headers` runs BEFORE `sanitize_lyrics`** for LRCLIB — sanitize only handles HTML/@mentions, not LRC metadata lines; use LRCLIB `/api/search` (not `/api/get`) — robust to missing duration, returns a relevance-sorted array (Phase 12 Pitfalls 1/2)
- **Auto-queue hallucination check uses token-set containment, not `difflib`** — YouTube titles are longer than clean names, so a subset check is the semantically correct rejection test for a hallucinated track (`logic/autoqueue.py`, D-12)

**Phases 13–17 (taste memory, music brain, RAG reach, proactive callbacks, vision):**
- **`taste_episode` is a new `kind`, not a new table or code path** — `MemoryService.recall/remember/distill` is kind-agnostic by design; `MEMORY_DECAY_DAYS_BY_KIND` is a NEW mapping (not a mutation of `MEMORY_DECAY_DAYS`) so every Phase 11 kind falls back unchanged (Phase 13)
- **`remember()` self-refreshes `expires_at` on dedup ONLY for kinds in `MEMORY_DECAY_DAYS_BY_KIND`** — the D-05 fix; Phase 11 kinds stay byte-identical. `refresh_memory_expiry` is an `expires_at`-only UPDATE sibling to `bump_memory_hit` (never touches hit_count/salience/last_seen_at)
- **`taste_distill_batch` runs at `TASTE_DISTILL_BATCH_HOUR` (05:00 UTC), the only free slot** distinct from cache_cleanup/memory_sweep/memory_distill_batch/ytdlp_update — no Neon thundering-herd. It carries `guild_id` through to `distill_and_remember` (unlike `daily_batch`'s `None`) since taste is guild-scoped listening (D-06/D-07)
- **`search_memories`/`recall` `kind` param defaults to `None` and OMITS the SQL clause entirely when unset** (never `kind IS NULL`) — byte-identical to pre-Phase-14 behavior; the guild-scoped `expires_at` search scoping is `user_id`-only, so a cross-kind sweep must not corrupt another kind's expiry (Phase 13 CR-01 scar)
- **`/discover` anchor derives from guild-scoped `song_history` (`get_user_top_artist`), NOT the guild-less `user_artist_counts`** (OQ2 Option B); co-occurrence is a same-guild-calendar-day aggregate with no per-user attribution — multi-user-safe, never leaks one user's history into another's results (Phase 14)
- **`select_positive_taste_context` checks the cap BEFORE appending** (not after) so `cap=0` returns `[]` — off-by-one scar found writing the cap=0 test (Phase 14)
- **D-01: `/ask` and `/roast` recall on EVERY invocation (gate removed); ambient surfaces (`events.py`, `music.py`) keep the `MEMORY_CALLBACK_CHANCE` gate** — `test_ambient_recall_cadence.py` locks this split. Removing the gate deleted `import random` from `cogs/ai.py` entirely (assert behaviorally, don't `patch("cogs.ai.random")`) (Phase 15)
- **`list_user_memories` callers pass `MEMORY_MAX_PER_USER`, never `MEMORY_INJECT_CAP`** — else the `/memory view` truncates below what `forget` erases (Phase 15 T-15-04)
- **Proactive gate (`logic/proactive.py`) implements only opt-out + chance + daily-cap; the async recall-floor step lives in cog glue, not the pure logic** — keep the seam pure. `PROACTIVE_CALLBACK_CHANCE=0.10` is strictly below both ambient cadences, enforced by a rarity-invariant test (Phase 16)
- **Pitfall-1: `_generate_ambient_roast` has its OWN internal `MEMORY_CALLBACK_CHANCE` gate** — calling it from the proactive surface unmodified triple-gates. The fix is an optional `pre_recalled_memories` param (default `None` = byte-identical ambient path), passed as an if/else split around the internal recall block, NOT an early return (Phase 16)
- **Vision reuses a DEDICATED `_generate_vision_roast` (str|None), never the ambient always-str generator** — the ambient path collapses safety-block AND transport-failure into one `return fallback_line`, which would leak a visible template for a safety-blocked image (VIS-02). Success→line, transport-except→fallback, empty/blocked→`None` silent-skip. `chat()` already returns `None`-no-raise on empty/blocked (Phase 17)
- **Vision mime allowlist EXCLUDES gif** (Gemini image-understanding 400s on GIF) and normalizes `content_type` (strip `;charset=`, `None`→reject); the mime/size gate runs BEFORE `attachment.read()`/download; the free structural gate runs BEFORE the DB opt-out lookup (WR-01/02/03 close-out fixes, Phase 17)

**Phases 18–23 (per-guild config, onboarding, owner control plane, memory scoping, invite, portfolio):**
- **`search_memories`'s SQL placeholder numbers are computed from `len(params)`, not hardcoded** — two optional clauses now exist (`kind`, `guild_id`), each appended only when its arg is set; a future third optional clause must follow the same discipline or it will silently bind to the wrong `$N` (Phase 21)
- **`recall()` forwards `guild_id=` to `search_memories` ONLY when `guild_scoped=True`** — passing it unconditionally (even as `None`) would break existing narrow-signature test doubles/fakes across the recall call sites, and would risk emitting a degenerate `guild_id IS NULL`-only filter instead of omitting the clause entirely (Phase 21, following the Phase 14 `kind`-clause precedent)
- **`remember()`'s k=1 dedup search stays fully `user_id`-scoped — untouched by the Phase 21 guild-scoping work** (CR-13-01 scar); guild-scoping was deliberately added to the READ path (`recall`/`search_memories`) only, never to dedup or `MEMORY_MAX_PER_USER` cap-eviction, which stay global per-user budgets (Phase 21, D-02)
- **`purge_guild_data`'s four-table DELETE list is four hardcoded SQL literals, never a loop or a schema-catalog introspection** — a dynamic form would eventually and silently sweep up `guild_blocklist` too; the reviewability of the literal list IS the control (Phase 21, T-21-03)
- **`purge_guild_data` raises on failure by design (no internal try/except)** — the best-effort swallow lives at the `bot.py::on_guild_remove` call site, mirroring `on_guild_join`'s WR-04 discipline, keeping the helper itself honestly testable (Phase 21)
- **`ambient_roasts_enabled`/`vision_roasts_enabled` are threaded via a REQUIRED keyword-only `AmbientSurface` enum, not read ad hoc** — a surface must name itself (`ROAST`/`PRESENCE`/`VISION`) to resolve a channel, so a new ambient surface cannot silently bypass the per-guild toggle gate; `TypeError` on omission is the guardrail (Phase 19, D-22)
- **`build_invite_url()` is the ONLY invite-URL constructor and the one sanctioned `import discord` inside `logic/`** — every surface (the `/invite` embed, docs, the site) must derive from it; the CI drift-guard (`test_invite_drift_guard.py`, extended to `site/dist/` in Phase 23) fails the build on any drift and has a positive control proving it's not a no-op (Phase 22/23, INVITE-02)
- **`/invite` prefers `bot.application_id` over a hardcoded client id** so a fork emits its OWN invite; `INVITE_PERMISSIONS_VALUE=309240908864` is negatively asserted free of Administrator/Manage Guild/Manage Roles by a CI test — widen it only through that assertion (Phase 22)
- **CI (`.github/workflows/ci.yml`) is `pull_request` (never `pull_request_target`), top-level `permissions: contents: read`, zero secrets, pgvector service container** — this least-privilege posture is the standing contract; `pages.yml`/`release.yml` (Phase 23) are CI-gated and only `release.yml` (GHCR on `v*` tags) needs elevated scope (Phase 18/23)
