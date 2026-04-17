"""All configurable settings for Dexter. Single file, no database config."""

import os
from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent
AUDIO_CACHE_DIR = BASE_DIR / "data" / "cache"
LOG_DIR = BASE_DIR / "logs"

# --- Music ---
MAX_SONG_DURATION_SECONDS = 900       # 15 min
MAX_PLAYLIST_IMPORT = 50
AUDIO_QUALITY = "192"                 # kbps opus
AUDIO_CACHE_MAX_MB = 2048            # 2GB
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

# --- Error Logging ---
ERROR_LOG_CHANNEL_ID = int(os.getenv("ERROR_LOG_CHANNEL_ID", "0")) or None

# --- Bot ---
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
