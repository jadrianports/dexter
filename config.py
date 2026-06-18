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
MAX_SONG_DURATION_SECONDS = 900       # 15 min
MAX_PLAYLIST_IMPORT = 50
AUDIO_QUALITY = "192"                 # kbps opus
AUDIO_CACHE_MAX_MB = 512             # Koyeb 2GB ephemeral disk (K-07)
IDLE_TIMEOUT_SECONDS = 600           # 10 min before auto-leave
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
UNPROMPTED_ROAST_CHANCE = 0.30          # 30% on voice join/leave
LATE_NIGHT_ROAST_CHANCE = 0.50          # 50% on 1-5am joins
AMBIENT_ROAST_CEILING_SECONDS = 300     # max 1 ambient roast per 5 min per user
ROAST_COOLDOWN_SECONDS = 300            # same value, alias for clarity
REPEAT_SONG_ROAST_THRESHOLD = 3         # plays same song ≥3× today → always roast
LATE_NIGHT_HOURS = (1, 5)               # tuple[int,int]: hours 1-5 inclusive

# --- Phase 3: Milestones ---
MILESTONE_SONG_THRESHOLDS: list[int] = [100, 250, 500, 1000]
MILESTONE_STREAK_THRESHOLDS: list[int] = [7, 14, 30, 60, 100]

# --- Phase 3: Status & Idle ---
STATUS_ROTATION_INTERVAL_SECONDS = 300  # 5 min
IDLE_LONELINESS_THRESHOLD_SECONDS = 1800  # 30 min silence with humans in voice

# --- Phase 3: Lyrics & History ---
LYRICS_COOLDOWN_SECONDS = 10
LYRICS_PAGE_SIZE = 1500                 # chars per embed page
HISTORY_PAGE_SIZE = 10                  # songs per history page
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
DB_MAX_INACTIVE_CONN_LIFETIME = 240      # recycle before Neon 5-min scale-to-zero (K-04)
DB_STATEMENT_CACHE_SIZE = 0             # disable prepared stmts for PgBouncer tx-mode (K-04)


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
    return re.sub(r'\?.*$', '', dsn)
