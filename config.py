"""All configurable settings for Dexter. Single file, no database config."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env before reading any environment variables below. config.py is imported
# (e.g. by bot.py) before that entry point calls load_dotenv(), so without this the
# import-time getenv calls (DEXTER_CHANNEL_ID, OWNER_ID, etc.) would miss .env values.
load_dotenv()

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent
AUDIO_CACHE_DIR = BASE_DIR / "data" / "cache"
LOG_DIR = BASE_DIR / "logs"

# --- Music ---
MAX_SONG_DURATION_SECONDS = 900  # 15 min
MAX_PLAYLIST_IMPORT = 50
AUDIO_QUALITY = "192"  # kbps opus
AUDIO_CACHE_MAX_MB = 512  # Koyeb 2GB ephemeral disk (K-07)
IDLE_TIMEOUT_SECONDS = 600  # 10 min before auto-leave
DOWNLOAD_TIMEOUT_SECONDS = 10
SEARCH_RESULTS_COUNT = 5

# --- Logging ---
LOG_LEVEL = "INFO"
LOG_RETENTION_DAYS = 14

# --- Cooldowns (seconds) ---
PLAY_COOLDOWN_SECONDS = 2
SKIP_COOLDOWN_SECONDS = 2
HELP_COOLDOWN_SECONDS = 5

# --- AI ---
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_RPM_LIMIT = 15
MAX_AI_RESPONSE_LENGTH = 500
ASK_COOLDOWN_SECONDS = 5

# --- Image Generation ---
IMAGEN_MODEL = "gemini-2.5-flash-image"
IMAGINE_COOLDOWN_SECONDS = 30
MAX_IMAGES_PER_USER_PER_DAY = 10

# --- Mood System ---
MOOD_NORMAL_THRESHOLD = 15
MOOD_TIRED_THRESHOLD = 30
MOOD_EXHAUSTED_THRESHOLD = 50

# --- Auto-Queue ---
AUTO_QUEUE_MAX_ROUNDS = 3
AUTO_QUEUE_SONGS_PER_ROUND = 3

# --- Phase 3: Personality / Ambient Channel ---
DEXTER_CHANNEL_ID = int(os.getenv("DEXTER_CHANNEL_ID") or "0") or None
STREAK_TIMEZONE = os.getenv("STREAK_TIMEZONE") or "America/New_York"  # IANA tz; override via env

# --- Phase 3: Roasts & Personality ---
UNPROMPTED_ROAST_CHANCE = 0.30  # 30% on voice join/leave
LATE_NIGHT_ROAST_CHANCE = 0.50  # 50% on 1-5am joins
AMBIENT_ROAST_CEILING_SECONDS = 300  # max 1 ambient roast per 5 min per user
ROAST_COOLDOWN_SECONDS = 30  # Phase 8: /roast slash command per-invoker cooldown (D-04)
REPEAT_SONG_ROAST_THRESHOLD = 3  # plays same song ≥3× today → always roast
LATE_NIGHT_HOURS = (1, 5)  # tuple[int,int]: hours 1-5 inclusive

# --- Phase 3: Milestones ---
MILESTONE_SONG_THRESHOLDS: list[int] = [100, 250, 500, 1000]
MILESTONE_STREAK_THRESHOLDS: list[int] = [7, 14, 30, 60, 100]

# --- Phase 3: Status & Idle ---
STATUS_ROTATION_INTERVAL_SECONDS = 300  # 5 min
IDLE_LONELINESS_THRESHOLD_SECONDS = 1800  # 30 min silence with humans in voice

# --- Phase 3: Lyrics & History ---
LYRICS_COOLDOWN_SECONDS = 10
LYRICS_PAGE_SIZE = 1500  # chars per embed page
HISTORY_PAGE_SIZE = 10  # songs per history page
HISTORY_FETCH_LIMIT = 50

# --- Error Logging ---
ERROR_LOG_CHANNEL_ID = int(os.getenv("ERROR_LOG_CHANNEL_ID") or "0") or None

# --- Bot ---
OWNER_ID = int(os.getenv("OWNER_ID") or "0")

# --- Phase 4: Database (Postgres) ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dexter:dexter@localhost:5432/dexter")
DB_POOL_MIN = 2
DB_POOL_MAX = 5

# --- Phase 4: Queue persistence ---
MAX_QUEUE_SIZE_PER_GUILD = 500

# --- Phase 4: Message buffer ---
MESSAGE_BUFFER_TTL_HOURS = 24

# --- Phase 4: Keep-alive / down-detection ---
HEALTHCHECK_URL = os.getenv("HEALTHCHECK_URL", "")

# --- Phase 5: Neon pool tuning (K-04) ---
DB_MAX_INACTIVE_CONN_LIFETIME = 240  # recycle before Neon 5-min scale-to-zero (K-04)
DB_STATEMENT_CACHE_SIZE = 0  # disable prepared stmts for PgBouncer tx-mode (K-04)


# --- Phase 7: Player UX & Filters ---
# Audio filter presets: name → FFmpeg -af chain string.
# "off" is not a key — off means no filter (passthrough default, D-12).
# 48000 = Discord opus sample rate.
FFMPEG_FILTERS: dict[str, str] = {
    "bassboost": "bass=g=8",
    "nightcore": "asetrate=48000*1.25,aresample=48000",
    "slowed+reverb": "asetrate=48000*0.85,aresample=48000,aecho=0.8:0.9:1000:0.3",
    "8d": "apulsator=hz=0.09",
}

# Favorites / playlists caps (D-21, D-28) — 25 fits a single Discord select menu
FAVORITES_MAX_PER_USER = 25
PLAYLISTS_MAX_PER_USER = 25
PLAYLIST_NAME_MAX_LENGTH = 60

# Phase 7 cooldowns (seconds)
SEEK_COOLDOWN_SECONDS = 2
FILTER_COOLDOWN_SECONDS = 5
FAVORITE_COOLDOWN_SECONDS = 2


# --- Phase 6: Speed & Caching ---
PREFETCH_TIMEOUT_SECONDS = 45  # generous budget for background prefetch (D-10)
RES_CACHE_TTL_DAYS = 14  # resolution cache TTL in days (D-07)
SPONSORBLOCK_CATEGORIES: frozenset = frozenset(
    {"sponsor", "selfpromo", "intro", "outro", "interaction", "music_offtopic"}
)  # D-14 SponsorBlock categories for download-time removal
PERF_ROLLING_WINDOW = 50  # rolling aggregate sample count (D-18)


# --- Phase 8: Social & Ops ---
LEADERBOARD_TOP_N = 5  # top-N per leaderboard section (D-13)


# --- Phase 12: Richer Music/UX ---
JAMS_PER_GUILD_MAX = 25  # per-guild jam cap (mirrors PLAYLISTS_MAX_PER_USER, D-05)
SKIP_STATS_MIN_PLAYS = 5  # min data points before showing skip rate (D-08)
AUTO_QUEUE_SEARCH_CANDIDATES = 3  # YouTube candidates per auto-queue suggestion (D-13)
# Note: reuse PLAYLIST_NAME_MAX_LENGTH (60) for jam names — no new knob needed (D-05)


# --- Phase 9: Reliability & Ops Hardening ---
# D-01: 503 when degraded (strict) vs legacy 200
HEALTH_STRICT_STATUS: bool = os.getenv("HEALTH_STRICT_STATUS", "true").lower() != "false"
DB_COMMAND_TIMEOUT_SECONDS: int = 30  # D-07: replaces hardcoded 30 in bot.py create_pool
INIT_WATCHDOG_TIMEOUT_SECONDS: int = 120  # D-06: asyncio.wait_for wrap on _initialize_once
SYNC_TIMEOUT_SECONDS: int = 30  # D-05: asyncio.wait_for wrap on bot.tree.sync()
TASK_ERROR_CHANNEL_COOLDOWN_SECONDS: int = 300  # D-04: dedup window per (task_name, exc_type)
YTDLP_RETRY_BACKOFF_SECONDS: float = 1.0  # D-08: per-attempt sleep in search/extract retry
YTDLP_MAX_QUICK_RETRIES: int = 2  # D-08: attempts before falling through to update path
# WR-03: bound the /health DB probe (acquire+SELECT 1) so a cold/exhausted Neon
# pool degrades fast instead of hanging
HEALTH_DB_PROBE_TIMEOUT: float = 3.0


# --- Phase 11: RAG Long-Term Memory ---
EMBEDDING_MODEL = "gemini-embedding-001"  # canonical model @ 768d (text-embedding-004 sunset 2026-01-14)
EMBED_DIM = 768  # embedding vector dimension
# embedding quota — SEPARATE from the 15 RPM GEMINI_RPM_LIMIT (A2 / Critical Rule 1)
EMBED_RPM_LIMIT = 60
MEMORY_TOP_K = 8  # tuned via 11-02 spike 2026-06-29
# tuned via 11-02 spike 2026-06-29 (high-precision floor; relevant 0.58-0.77,
# decoys 0.53-0.66 — no clean global sep, keep tight)
MEMORY_SIMILARITY_FLOOR = 0.70
# tuned via 11-02 spike 2026-06-29 (raised from 0.90; near-dup pairs scored
# 0.937/0.955, distinct facts max 0.79)
MEMORY_DEDUP_THRESHOLD = 0.92
MEMORY_INJECT_CAP = 3  # tuned via 11-02 spike 2026-06-29
MEMORY_MAX_PER_USER = 150  # tuned via 11-02 spike 2026-06-29
MEMORY_DECAY_DAYS = 90  # tuned via 11-02 spike 2026-06-29
# sweep threshold: facts below this salience are eligible for expiry (D-08 /
# T-11-07b); retains repeat_song=0.5+, sweeps auto_queue_ignored=0.4/daily_batch=0.2
MEMORY_DECAY_SALIENCE_FLOOR = 0.5
MEMORY_RERANK_RELEVANCE_WEIGHT = 1.0  # tuned via 11-02 spike 2026-06-29
MEMORY_RERANK_RECENCY_WEIGHT = 0.5  # tuned via 11-02 spike 2026-06-29
MEMORY_RERANK_SALIENCE_WEIGHT = 0.7  # tuned via 11-02 spike 2026-06-29
MEMORY_RERANK_NOVELTY_WEIGHT = 0.5  # tuned via 11-02 spike 2026-06-29
MEMORY_CALLBACK_CHANCE = 0.35  # D-04 occasional-payoff cadence; tuned via 11-02 spike 2026-06-29
MEMORY_DISTILL_BATCH_HOUR = 3  # daily distill-batch hour (UTC)
MEMORY_VIEW_PAGE_SIZE = 3800  # chars per /memory view page (RAG-03, Phase 15;
# char-budget like LYRICS_PAGE_SIZE, not fact
# count — WR-03 fix, stays under the 4096-char
# embed description limit)

# Ordinal salience base weights for each memory event kind (D-07 hybrid salience).
# These are intentionally ordinal — not finely tuned (RESEARCH.md Q3 / A5).
# milestone > late_night > repeat_song > auto_queue_ignored >= daily_batch.
MEMORY_SALIENCE_BASE_WEIGHTS: dict[str, float] = {
    "milestone": 1.0,  # crossed a song/streak milestone — high personal significance
    "late_night": 0.7,  # activity at 1–5am — notable behavioural signal
    "repeat_song": 0.5,  # same song queued 3+ times in a day — strong preference signal
    "auto_queue_ignored": 0.4,  # user skipped AI auto-queued track — negative taste signal
    "daily_batch": 0.2,  # background distill from message buffer — lower-confidence
    "taste_episode": 0.4,  # D-04: MUST stay < MEMORY_DECAY_SALIENCE_FLOOR (0.5) — taste rows
    # are genuinely sweep-eligible so fads age out (D-05 self-refresh design)
}


# --- Phase 13: Semantic Music Memory ---
# D-03: shorter half-life than MEMORY_DECAY_DAYS=90 (Pitfall 5 — stale taste surfaced as current)
TASTE_DECAY_DAYS = 30
# D-06: distinct UTC slot, clear of existing 02:30/03:00/04:00 loops (no Neon thundering-herd)
TASTE_DISTILL_BATCH_HOUR = 5
TASTE_LOOKBACK_DAYS = 7  # D-07: rolling recent window for obsession/new-arrival detection
# bounded "before-window" span for steady/new-arrival baseline detection (index-friendly)
TASTE_BASELINE_DAYS = 90
TASTE_MIN_ACTIVITY_TRACKS = 5  # D-08: min tracks in window to bother distilling — skip inactive users
TASTE_OBSESSION_MIN_PLAYS = 5  # plays_in_window at/above this → OBSESSION pattern
TASTE_NEW_ARRIVAL_MIN_PLAYS = 3  # plays_in_window at/above this (with zero baseline plays) → NEW_ARRIVAL pattern
TASTE_STEADY_MIN_BASELINE = 5  # plays_before_window at/above this → eligible for STEADY/DROPPED_OFF
TASTE_BAND_HEAVY_PLAYS = 5  # qualitative band threshold: "played heavily" vs "a few times"
TASTE_BAND_FEW_PLAYS = 2  # qualitative band threshold: floor for "a few times" phrasing

# Per-kind decay-horizon override (D-03). Kinds absent from this map fall back to
# MEMORY_DECAY_DAYS (90), preserving Phase 11 semantics unchanged. Consumed by
# logic.taste.resolve_decay_days and the memory-service self-refresh (plan 13-03).
MEMORY_DECAY_DAYS_BY_KIND: dict[str, int] = {
    "taste_episode": TASTE_DECAY_DAYS,
}


# --- Phase 14: Smarter Music Brain (BRAIN-01/02/03) ---
# All six knobs below are directional / Claude's-discretion priors per CONTEXT.md —
# not derived from any measured constraint, safe to retune later without a design change.
AUTO_QUEUE_SKIP_LOOKBACK_DAYS = 7  # D-01: recently-skipped window, days
AUTO_QUEUE_SKIP_HINT_CAP = 15  # D-01: max rows in the negative-hint block
AUTO_QUEUE_POSITIVE_TASTE_CAP = 4  # D-03: max injected taste_episode facts
DISCOVER_ADJACENT_COUNT = 3  # D-04: max /discover adjacent artists surfaced
DISCOVER_COOCCURRENCE_WINDOW_DAYS = 90  # D-04: get_artist_cooccurrence recency bound, days
JAM_SUGGEST_CANDIDATE_COUNT = 3  # D-06: /jam suggest candidate additions requested


# --- Phase 16: Proactive Memory Callbacks ---
# D-02: chance MUST stay strictly below both ambient cadences (UNPROMPTED_ROAST_CHANCE
# = 0.30, MEMORY_CALLBACK_CHANCE = 0.35) — this is the rarest of the three cadences
# (locked by tests/test_proactive_logic.py::test_proactive_chance_is_rarer_than_ambient).
# D-02: strictly < UNPROMPTED_ROAST_CHANCE (0.30) and < MEMORY_CALLBACK_CHANCE (0.35)
PROACTIVE_CALLBACK_CHANCE = 0.10
PROACTIVE_CALLBACK_DAILY_CAP = 1  # D-02: additive per-user, per-calendar-day ceiling


# --- Phase 17: Vision / Multimodal Roasting (VIS-01/02/03) ---
# D-04: VISION_ROAST_CHANCE MUST stay strictly below both ambient cadences
# (UNPROMPTED_ROAST_CHANCE = 0.30, MEMORY_CALLBACK_CHANCE = 0.35) — the rarest
# unprompted cadence (locked by tests/test_vision_logic.py::test_vision_chance_is_rarer_than_ambient).
# D-04: strictly < UNPROMPTED_ROAST_CHANCE (0.30) and < MEMORY_CALLBACK_CHANCE (0.35)
VISION_ROAST_CHANCE = 0.12
# per-user cooldown ceiling (passed to logic.roasts.cooldown_elapsed by the Wave-2 glue)
VISION_ROAST_COOLDOWN_SECONDS = 600
# 8MB raw — headroom below Gemini's 20MB combined inline-request cap after ~33% base64 inflation (RESEARCH Pitfall 4)
MAX_VISION_IMAGE_BYTES = 8 * 1024 * 1024
# image/gif DELIBERATELY excluded — Gemini image-understanding 400s on GIF (RESEARCH Pitfall 2)
VISION_MIME_ALLOWLIST = frozenset({"image/png", "image/jpeg", "image/webp"})
VISION_SAFETY_THRESHOLD = "BLOCK_MEDIUM_AND_ABOVE"  # D-01: real block — vision only
# D-01: permissive-but-explicit — /ask + /imagine + every non-image chat() call (must NOT regress edgy output)
TEXT_SAFETY_THRESHOLD = "BLOCK_ONLY_HIGH"


# --- Phase 20: Owner Control Plane & Rate Observability (OWNER-01/RATE-01) ---
# char-budget per /guilds list page — mirrors the MEMORY_VIEW_PAGE_SIZE idiom
# (D-10: no silent truncation, paginate instead)
GUILDS_LIST_PAGE_SIZE = 1800


# --- Phase 22: Invite Plumbing (INVITE-01/02) ---
# A Discord client/application ID is PUBLIC BY DESIGN — it is visible in every invite
# link ever handed out — so committing a default here leaks nothing. This is load-bearing,
# not cosmetic: the Phase 18 CI gate runs with ZERO secrets and no `.env`, and the 22-03
# drift-guard test must still resolve a real client ID there (D-04). The env override keeps
# a fork pointed at its own Discord application.
DISCORD_CLIENT_ID = int(os.getenv("DISCORD_CLIENT_ID") or "1492588698364018898")

# The ten-permission least-privilege invite bitfield (D-01, amended by D-09 to add the two
# /autolyrics thread permissions). Each permission is code-proven, not aspirational:
#   view_channel             - prerequisite for every ambient/message surface
#   send_messages            - every cog
#   embed_links               - 78 `embed=` sends across cogs/*.py
#   attach_files              - cogs/imagine.py:69-74 (discord.File upload)
#   add_reactions             - cogs/events.py:345,355,379 (👀 / 🫡 / 😐 reactions)
#   read_message_history      - cogs/music.py:833 (channel.fetch_message for now-playing edit)
#   connect                   - cogs/music.py:526 (member.voice.channel.connect())
#   speak                     - voice playback
#   create_public_threads     - cogs/music.py:938 (/autolyrics thread creation, D-09)
#   send_messages_in_threads  - cogs/music.py:950,958,965 (/autolyrics thread posts, D-09)
# The superseded 8-permission value 3263552 (pre-D-09) must NEVER be assigned to a constant.
# Locked by tests/test_invite_logic.py::test_bitfield_excludes_dangerous_permissions
# (no administrator/manage_guild/manage_roles/manage_channels/ban_members/kick_members)
# and test_bitfield_matches_ten_permission_derivation (the magic number is never trusted alone).
INVITE_PERMISSIONS_VALUE = 309240908864

# oauth_url() takes an Iterable[str] -- a bare string would iterate character-by-character.
INVITE_SCOPES: tuple[str, ...] = ("bot", "applications.commands")


def sanitize_database_url(dsn: str) -> str:
    """Strip asyncpg-incompatible query params from a Neon connection string.

    Neon's console DSN includes ?sslmode=require&channel_binding=require.
    asyncpg does not recognize channel_binding and may treat it as a Postgres
    GUC, causing an error. sslmode is handled via explicit ssl= kwarg in
    create_pool. Strips the entire query string; safe for non-Neon DSNs
    (no-op if no ? present).

    Pure function — fully unit-testable (K-05).
    """
    import re

    return re.sub(r"\?.*$", "", dsn)
