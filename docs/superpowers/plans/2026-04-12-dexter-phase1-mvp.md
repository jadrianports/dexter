# Dexter Phase 1 MVP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fully functional slash-command Discord music bot with YouTube search/playback, per-server queues, audio caching, SQLite tracking, and a clean layered architecture.

**Architecture:** Layered cog → service → model design. Services attached as bot attributes. Pure `app_commands` slash commands. Download-first audio with stream fallback. SQLite via aiosqlite for persistent tracking.

**Tech Stack:** Python 3.11+, discord.py >= 2.3.0, yt-dlp, FFmpeg, aiosqlite, python-dotenv, pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-04-12-dexter-phase1-design.md`

---

## File Map

| File | Responsibility | Task |
|------|---------------|------|
| `requirements.txt` | Python dependencies | 1 |
| `.env.example` | Env var template | 1 |
| `.gitignore` | Git ignores | 1 |
| `config.py` | All settings | 2 |
| `utils/logger.py` | Logging setup | 3 |
| `utils/formatters.py` | Duration/progress formatting | 4 |
| `tests/test_formatters.py` | Formatter tests | 4 |
| `models/queue.py` | Track, LoopMode, MusicQueue | 5 |
| `tests/test_queue.py` | Queue model tests | 5 |
| `database.py` | SQLite schema + query helpers | 6 |
| `tests/test_database.py` | Database tests (in-memory) | 6 |
| `services/youtube.py` | yt-dlp search/extract/download | 7 |
| `tests/test_youtube.py` | YouTube service tests (mocked) | 7 |
| `services/audio.py` | FFmpeg sources + cache mgmt | 8 |
| `tests/test_audio.py` | Audio cache logic tests | 8 |
| `utils/embeds.py` | Discord embed builders | 9 |
| `cogs/help.py` | /help slash command | 10 |
| `cogs/music.py` | All music slash commands | 11-12 |
| `bot.py` | Entry point, wiring, bg tasks | 13 |

---

### Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `data/cache/.gitkeep`

- [ ] **Step 1: Create `requirements.txt`**

```
discord.py>=2.3.0
yt-dlp
aiosqlite
python-dotenv
PyNaCl
pytest
pytest-asyncio
```

Note: `PyNaCl` is required by discord.py for voice support.

- [ ] **Step 2: Create `.env.example`**

```
DISCORD_TOKEN=
# GEMINI_API_KEY=     # Phase 2
# GENIUS_TOKEN=       # Phase 3
```

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.pyc
.env
data/cache/*.opus
logs/
venv/
.pytest_cache/
*.egg-info/
dist/
build/
```

- [ ] **Step 4: Create directory structure with placeholders**

```bash
mkdir -p cogs services models utils tests data/cache logs
touch data/cache/.gitkeep
```

- [ ] **Step 5: Create virtual environment and install dependencies**

```bash
python -m venv venv
source venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
```

- [ ] **Step 6: Verify installation**

```bash
python -c "import discord; print(discord.__version__)"
python -c "import yt_dlp; print(yt_dlp.version.__version__)"
python -c "import aiosqlite; print(aiosqlite.__version__)"
```

Expected: version numbers printed, no import errors.

- [ ] **Step 7: Commit**

```bash
git init
git add requirements.txt .env.example .gitignore data/cache/.gitkeep
git commit -m "feat: project scaffolding with dependencies and directory structure"
```

---

### Task 2: Configuration Module

**Files:**
- Create: `config.py`

- [ ] **Step 1: Create `config.py`**

```python
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

# --- Bot ---
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
```

- [ ] **Step 2: Commit**

```bash
git add config.py
git commit -m "feat: add config module with all Phase 1 settings"
```

---

### Task 3: Logger Utility

**Files:**
- Create: `utils/__init__.py`
- Create: `utils/logger.py`

- [ ] **Step 1: Create `utils/__init__.py`**

Empty file to make `utils` a package:

```python
```

- [ ] **Step 2: Create `utils/logger.py`**

```python
"""File logging setup for Dexter."""

import logging
from logging.handlers import TimedRotatingFileHandler

import config


def setup_logger(name: str = "dexter") -> logging.Logger:
    """Configure and return the application logger.

    - Logs to {LOG_DIR}/dexter.log with daily rotation.
    - Also logs to console (stderr) during development.
    """
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler — daily rotation, keep LOG_RETENTION_DAYS days
    file_handler = TimedRotatingFileHandler(
        config.LOG_DIR / "dexter.log",
        when="midnight",
        interval=1,
        backupCount=config.LOG_RETENTION_DAYS,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler — always on during development
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


log = setup_logger()
```

- [ ] **Step 3: Verify logger works**

```bash
python -c "from utils.logger import log; log.info('Logger initialized'); log.warning('Test warning')"
```

Expected: formatted log line printed to console AND written to `logs/dexter.log`.

- [ ] **Step 4: Commit**

```bash
git add utils/__init__.py utils/logger.py
git commit -m "feat: add file logger with daily rotation and console output"
```

---

### Task 4: Formatters Utility + Tests

**Files:**
- Create: `utils/formatters.py`
- Create: `tests/__init__.py`
- Create: `tests/test_formatters.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/__init__.py` (empty):

```python
```

Create `tests/test_formatters.py`:

```python
"""Tests for duration formatting and progress bar rendering."""

from utils.formatters import format_duration, progress_bar


class TestFormatDuration:
    def test_seconds_only(self):
        assert format_duration(45) == "0:45"

    def test_minutes_and_seconds(self):
        assert format_duration(200) == "3:20"

    def test_hours(self):
        assert format_duration(3661) == "1:01:01"

    def test_zero(self):
        assert format_duration(0) == "0:00"

    def test_exact_minute(self):
        assert format_duration(60) == "1:00"

    def test_single_digit_seconds_padded(self):
        assert format_duration(65) == "1:05"


class TestProgressBar:
    def test_half_progress(self):
        bar = progress_bar(100, 200, length=10)
        assert bar == "▓▓▓▓▓░░░░░ 1:40 / 3:20"

    def test_zero_progress(self):
        bar = progress_bar(0, 200, length=10)
        assert bar == "░░░░░░░░░░ 0:00 / 3:20"

    def test_full_progress(self):
        bar = progress_bar(200, 200, length=10)
        assert bar == "▓▓▓▓▓▓▓▓▓▓ 3:20 / 3:20"

    def test_over_total_clamps(self):
        bar = progress_bar(300, 200, length=10)
        assert bar == "▓▓▓▓▓▓▓▓▓▓ 3:20 / 3:20"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_formatters.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'utils.formatters'`

- [ ] **Step 3: Implement `utils/formatters.py`**

```python
"""Duration formatting and progress bar rendering."""


def format_duration(seconds: int) -> str:
    """Format seconds into H:MM:SS or M:SS string."""
    if seconds < 0:
        seconds = 0
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def progress_bar(current: int, total: int, length: int = 15) -> str:
    """Render a text progress bar with timestamps.

    Returns: '▓▓▓▓▓░░░░░ 1:40 / 3:20'
    """
    if total <= 0:
        filled = 0
        clamped = 0
    else:
        clamped = min(current, total)
        filled = round(length * clamped / total)

    bar = "▓" * filled + "░" * (length - filled)
    return f"{bar} {format_duration(clamped)} / {format_duration(total)}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_formatters.py -v
```

Expected: all 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add utils/formatters.py tests/__init__.py tests/test_formatters.py
git commit -m "feat: add duration formatter and progress bar with tests"
```

---

### Task 5: Queue Model + Tests

**Files:**
- Create: `models/__init__.py`
- Create: `models/queue.py`
- Create: `tests/test_queue.py`

- [ ] **Step 1: Write the failing tests**

Create `models/__init__.py` (empty):

```python
```

Create `tests/test_queue.py`:

```python
"""Tests for the MusicQueue model."""

import pytest
from models.queue import Track, LoopMode, MusicQueue


def make_track(video_id: str = "abc123", title: str = "Test Song", **kwargs) -> Track:
    """Helper to create a Track with defaults."""
    defaults = {
        "video_id": video_id,
        "title": title,
        "artist": "Test Artist",
        "url": f"https://youtube.com/watch?v={video_id}",
        "duration_seconds": 200,
        "requested_by": 12345,
        "was_auto_queued": False,
    }
    defaults.update(kwargs)
    return Track(**defaults)


class TestMusicQueueAdd:
    def test_add_track(self):
        q = MusicQueue(guild_id=1)
        track = make_track()
        q.add(track)
        assert len(q.tracks) == 1
        assert q.tracks[0] is track

    def test_add_multiple(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track(video_id="a"))
        q.add(make_track(video_id="b"))
        assert len(q.tracks) == 2


class TestMusicQueueSkip:
    def test_skip_advances_index(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track(video_id="a"))
        q.add(make_track(video_id="b"))
        q.current_index = 0
        result = q.skip()
        assert q.current_index == 1
        assert result is not None

    def test_skip_at_end_returns_none_loop_off(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track())
        q.current_index = 0
        result = q.skip()
        assert result is None

    def test_skip_at_end_wraps_loop_queue(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track(video_id="a"))
        q.add(make_track(video_id="b"))
        q.current_index = 1
        q.loop_mode = LoopMode.QUEUE
        result = q.skip()
        assert q.current_index == 0
        assert result is not None

    def test_skip_ignores_single_loop(self):
        """Skip always advances, even in SINGLE loop mode."""
        q = MusicQueue(guild_id=1)
        q.add(make_track(video_id="a"))
        q.add(make_track(video_id="b"))
        q.current_index = 0
        q.loop_mode = LoopMode.SINGLE
        result = q.skip()
        assert q.current_index == 1


class TestMusicQueueAdvance:
    def test_advance_repeats_on_single_loop(self):
        """Natural end (advance) repeats the track on SINGLE loop."""
        q = MusicQueue(guild_id=1)
        q.add(make_track(video_id="a"))
        q.add(make_track(video_id="b"))
        q.current_index = 0
        q.loop_mode = LoopMode.SINGLE
        result = q.advance()
        assert q.current_index == 0
        assert result is not None

    def test_advance_moves_on_loop_off(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track(video_id="a"))
        q.add(make_track(video_id="b"))
        q.current_index = 0
        result = q.advance()
        assert q.current_index == 1

    def test_advance_wraps_on_loop_queue(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track(video_id="a"))
        q.add(make_track(video_id="b"))
        q.current_index = 1
        q.loop_mode = LoopMode.QUEUE
        result = q.advance()
        assert q.current_index == 0


class TestMusicQueuePrevious:
    def test_previous_decrements(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track(video_id="a"))
        q.add(make_track(video_id="b"))
        q.current_index = 1
        result = q.previous()
        assert q.current_index == 0
        assert result is not None

    def test_previous_at_start_returns_none(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track())
        q.current_index = 0
        result = q.previous()
        assert result is None
        assert q.current_index == 0


class TestMusicQueueShuffle:
    def test_shuffle_only_upcoming(self):
        q = MusicQueue(guild_id=1)
        for i in range(10):
            q.add(make_track(video_id=str(i), title=f"Song {i}"))
        q.current_index = 3

        before_current = [t.video_id for t in q.tracks[: q.current_index + 1]]
        q.shuffle()
        after_current = [t.video_id for t in q.tracks[: q.current_index + 1]]

        # Tracks at and before current_index should be unchanged
        assert before_current == after_current

    def test_shuffle_empty_upcoming_noop(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track())
        q.current_index = 0
        q.shuffle()  # should not raise
        assert len(q.tracks) == 1


class TestMusicQueueClear:
    def test_clear_resets_everything(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track())
        q.current_index = 0
        q.is_playing = True
        q.loop_mode = LoopMode.QUEUE
        q.clear()
        assert q.tracks == []
        assert q.current_index == 0
        assert q.is_playing is False
        assert q.is_paused is False
        assert q.loop_mode == LoopMode.OFF


class TestMusicQueueGetCurrent:
    def test_get_current_returns_track(self):
        q = MusicQueue(guild_id=1)
        t = make_track()
        q.add(t)
        q.current_index = 0
        assert q.get_current() is t

    def test_get_current_empty_returns_none(self):
        q = MusicQueue(guild_id=1)
        assert q.get_current() is None

    def test_get_current_index_out_of_range(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track())
        q.current_index = 5
        assert q.get_current() is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_queue.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'models.queue'`

- [ ] **Step 3: Implement `models/queue.py`**

```python
"""Per-server music queue model."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum


class LoopMode(Enum):
    OFF = "off"
    SINGLE = "single"
    QUEUE = "queue"


@dataclass
class Track:
    """A single queued track. Stores the permanent YouTube URL, not a stream URL."""

    video_id: str
    title: str
    artist: str | None
    url: str
    duration_seconds: int
    requested_by: int
    was_auto_queued: bool = False
    thumbnail: str | None = None


class MusicQueue:
    """Per-server music queue. All index math and loop logic lives here."""

    def __init__(self, guild_id: int) -> None:
        self.guild_id = guild_id
        self.tracks: list[Track] = []
        self.current_index: int = 0
        self.loop_mode: LoopMode = LoopMode.OFF
        self.is_playing: bool = False
        self.is_paused: bool = False
        self._now_playing_message_id: int | None = None

    def add(self, track: Track) -> int:
        """Add a track to the end of the queue. Returns its index."""
        self.tracks.append(track)
        return len(self.tracks) - 1

    def get_current(self) -> Track | None:
        """Return the current track, or None if queue is empty/index out of range."""
        if 0 <= self.current_index < len(self.tracks):
            return self.tracks[self.current_index]
        return None

    def skip(self) -> Track | None:
        """Advance to next track (manual skip — ignores SINGLE loop).

        Returns the next Track, or None if queue is exhausted.
        """
        return self._advance(respect_single_loop=False)

    def advance(self) -> Track | None:
        """Advance to next track (natural song end — respects SINGLE loop).

        Returns the next Track, or None if queue is exhausted.
        """
        return self._advance(respect_single_loop=True)

    def _advance(self, respect_single_loop: bool) -> Track | None:
        if not self.tracks:
            return None

        if respect_single_loop and self.loop_mode == LoopMode.SINGLE:
            return self.get_current()

        next_index = self.current_index + 1

        if next_index >= len(self.tracks):
            if self.loop_mode == LoopMode.QUEUE:
                next_index = 0
            else:
                return None

        self.current_index = next_index
        return self.get_current()

    def previous(self) -> Track | None:
        """Go to previous track. Returns None if already at start."""
        if self.current_index <= 0:
            return None
        self.current_index -= 1
        return self.get_current()

    def shuffle(self) -> None:
        """Shuffle tracks after current_index. Current and past tracks untouched."""
        start = self.current_index + 1
        if start >= len(self.tracks):
            return
        upcoming = self.tracks[start:]
        random.shuffle(upcoming)
        self.tracks[start:] = upcoming

    def clear(self) -> None:
        """Reset the queue to empty state."""
        self.tracks.clear()
        self.current_index = 0
        self.is_playing = False
        self.is_paused = False
        self.loop_mode = LoopMode.OFF
        self._now_playing_message_id = None

    def upcoming(self) -> list[Track]:
        """Return tracks after the current one."""
        return self.tracks[self.current_index + 1:]

    def __len__(self) -> int:
        return len(self.tracks)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_queue.py -v
```

Expected: all 17 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add models/__init__.py models/queue.py tests/test_queue.py
git commit -m "feat: add MusicQueue model with Track, LoopMode, and full test coverage"
```

---

### Task 6: Database Module + Tests

**Files:**
- Create: `database.py`
- Create: `tests/test_database.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_database.py`:

```python
"""Tests for database schema and query helpers using in-memory SQLite."""

import pytest
import pytest_asyncio
import aiosqlite

from database import init_db, log_song, update_artist_count, update_user_profile, increment_daily_stat


@pytest_asyncio.fixture
async def db():
    """Create an in-memory database with schema for each test."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db(conn)
    yield conn
    await conn.close()


class TestSchema:
    @pytest.mark.asyncio
    async def test_tables_created(self, db):
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]
        assert "bot_daily_stats" in tables
        assert "song_history" in tables
        assert "user_artist_counts" in tables
        assert "user_profiles" in tables

    @pytest.mark.asyncio
    async def test_init_db_idempotent(self, db):
        """Calling init_db twice should not fail."""
        await init_db(db)


class TestLogSong:
    @pytest.mark.asyncio
    async def test_log_song_inserts_row(self, db):
        await log_song(db, guild_id="g1", user_id="u1", title="Test Song",
                       artist="Test Artist", url="https://yt.com/1", duration=200)
        cursor = await db.execute("SELECT * FROM song_history")
        rows = await cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["title"] == "Test Song"
        assert rows[0]["artist"] == "Test Artist"
        assert rows[0]["guild_id"] == "g1"

    @pytest.mark.asyncio
    async def test_log_song_null_artist(self, db):
        await log_song(db, guild_id="g1", user_id="u1", title="No Artist",
                       artist=None, url="https://yt.com/2", duration=100)
        cursor = await db.execute("SELECT artist FROM song_history")
        row = await cursor.fetchone()
        assert row["artist"] is None


class TestUpdateArtistCount:
    @pytest.mark.asyncio
    async def test_first_play_creates_row(self, db):
        await update_artist_count(db, user_id="u1", artist="Radiohead")
        cursor = await db.execute("SELECT * FROM user_artist_counts WHERE user_id='u1'")
        row = await cursor.fetchone()
        assert row["play_count"] == 1

    @pytest.mark.asyncio
    async def test_second_play_increments(self, db):
        await update_artist_count(db, user_id="u1", artist="Radiohead")
        await update_artist_count(db, user_id="u1", artist="Radiohead")
        cursor = await db.execute(
            "SELECT play_count FROM user_artist_counts WHERE user_id='u1' AND artist='Radiohead'"
        )
        row = await cursor.fetchone()
        assert row["play_count"] == 2

    @pytest.mark.asyncio
    async def test_skip_null_artist(self, db):
        await update_artist_count(db, user_id="u1", artist=None)
        cursor = await db.execute("SELECT count(*) as cnt FROM user_artist_counts")
        row = await cursor.fetchone()
        assert row["cnt"] == 0


class TestUpdateUserProfile:
    @pytest.mark.asyncio
    async def test_first_time_creates_profile(self, db):
        await update_user_profile(db, user_id="u1", username="jake")
        cursor = await db.execute("SELECT * FROM user_profiles WHERE user_id='u1'")
        row = await cursor.fetchone()
        assert row["username"] == "jake"
        assert row["total_songs_queued"] == 1

    @pytest.mark.asyncio
    async def test_repeat_increments_songs(self, db):
        await update_user_profile(db, user_id="u1", username="jake")
        await update_user_profile(db, user_id="u1", username="jake")
        cursor = await db.execute("SELECT total_songs_queued FROM user_profiles WHERE user_id='u1'")
        row = await cursor.fetchone()
        assert row["total_songs_queued"] == 2


class TestIncrementDailyStat:
    @pytest.mark.asyncio
    async def test_increment_creates_row(self, db):
        await increment_daily_stat(db, "total_commands")
        cursor = await db.execute("SELECT * FROM bot_daily_stats")
        row = await cursor.fetchone()
        assert row["total_commands"] == 1

    @pytest.mark.asyncio
    async def test_increment_twice(self, db):
        await increment_daily_stat(db, "total_commands")
        await increment_daily_stat(db, "total_commands")
        cursor = await db.execute("SELECT total_commands FROM bot_daily_stats")
        row = await cursor.fetchone()
        assert row["total_commands"] == 2

    @pytest.mark.asyncio
    async def test_increment_songs_played(self, db):
        await increment_daily_stat(db, "total_songs_played")
        cursor = await db.execute("SELECT total_songs_played FROM bot_daily_stats")
        row = await cursor.fetchone()
        assert row["total_songs_played"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_database.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'database'`

- [ ] **Step 3: Implement `database.py`**

```python
"""SQLite database initialization and query helpers."""

from __future__ import annotations

from datetime import date

import aiosqlite

from utils.logger import log

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    total_songs_queued INTEGER DEFAULT 0,
    first_seen_at TEXT DEFAULT (datetime('now')),
    last_active_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS song_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT,
    url TEXT NOT NULL,
    duration_seconds INTEGER,
    queued_at TEXT DEFAULT (datetime('now')),
    was_skipped BOOLEAN DEFAULT 0,
    was_auto_queued BOOLEAN DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_history_guild ON song_history(guild_id, queued_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_user ON song_history(user_id, queued_at DESC);

CREATE TABLE IF NOT EXISTS user_artist_counts (
    user_id TEXT NOT NULL,
    artist TEXT NOT NULL,
    play_count INTEGER DEFAULT 1,
    PRIMARY KEY (user_id, artist)
);

CREATE TABLE IF NOT EXISTS bot_daily_stats (
    date TEXT PRIMARY KEY,
    total_commands INTEGER DEFAULT 0,
    total_songs_played INTEGER DEFAULT 0,
    total_ai_queries INTEGER DEFAULT 0,
    total_images_generated INTEGER DEFAULT 0
);
"""


async def init_db(db: aiosqlite.Connection) -> None:
    """Create all tables if they don't exist."""
    await db.executescript(SCHEMA_SQL)
    await db.commit()
    log.info("Database schema initialized")


async def log_song(
    db: aiosqlite.Connection,
    *,
    guild_id: str,
    user_id: str,
    title: str,
    artist: str | None,
    url: str,
    duration: int,
) -> None:
    """Insert a song into the history."""
    await db.execute(
        """INSERT INTO song_history (guild_id, user_id, title, artist, url, duration_seconds)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (guild_id, user_id, title, artist, url, duration),
    )
    await db.commit()


async def update_artist_count(
    db: aiosqlite.Connection, *, user_id: str, artist: str | None
) -> None:
    """Increment the play count for an artist. Skips if artist is None."""
    if artist is None:
        return
    await db.execute(
        """INSERT INTO user_artist_counts (user_id, artist, play_count)
           VALUES (?, ?, 1)
           ON CONFLICT(user_id, artist) DO UPDATE SET play_count = play_count + 1""",
        (user_id, artist),
    )
    await db.commit()


async def update_user_profile(
    db: aiosqlite.Connection, *, user_id: str, username: str
) -> None:
    """Create or update a user profile, incrementing their song count."""
    await db.execute(
        """INSERT INTO user_profiles (user_id, username, total_songs_queued)
           VALUES (?, ?, 1)
           ON CONFLICT(user_id) DO UPDATE SET
               username = excluded.username,
               total_songs_queued = total_songs_queued + 1,
               last_active_at = datetime('now')""",
        (user_id, username),
    )
    await db.commit()


async def increment_daily_stat(db: aiosqlite.Connection, field: str) -> None:
    """Increment a field in today's daily stats row."""
    today = date.today().isoformat()
    allowed_fields = {"total_commands", "total_songs_played", "total_ai_queries", "total_images_generated"}
    if field not in allowed_fields:
        raise ValueError(f"Invalid stat field: {field}")

    await db.execute(
        f"""INSERT INTO bot_daily_stats (date, {field})
            VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET {field} = {field} + 1""",
        (today,),
    )
    await db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_database.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add database.py tests/test_database.py
git commit -m "feat: add SQLite database with schema and query helpers, full test coverage"
```

---

### Task 7: YouTube Service + Tests

**Files:**
- Create: `services/__init__.py`
- Create: `services/youtube.py`
- Create: `tests/test_youtube.py`

- [ ] **Step 1: Write the failing tests**

Create `services/__init__.py` (empty):

```python
```

Create `tests/test_youtube.py`:

```python
"""Tests for YouTubeService with mocked yt-dlp responses."""

import pytest
from unittest.mock import patch, MagicMock

from services.youtube import YouTubeService
from models.queue import Track


@pytest.fixture
def yt_service():
    return YouTubeService()


MOCK_SEARCH_RESULT = {
    "entries": [
        {
            "id": "abc123",
            "title": "Test Song - Test Artist",
            "url": "https://www.youtube.com/watch?v=abc123",
            "duration": 200,
            "thumbnails": [{"url": "https://i.ytimg.com/vi/abc123/default.jpg"}],
        },
        {
            "id": "def456",
            "title": "Another Song",
            "url": "https://www.youtube.com/watch?v=def456",
            "duration": 180,
            "thumbnails": [{"url": "https://i.ytimg.com/vi/def456/default.jpg"}],
        },
    ]
}

MOCK_EXTRACT_RESULT = {
    "id": "abc123",
    "title": "Test Song",
    "uploader": "Test Artist",
    "artist": "Test Artist",
    "webpage_url": "https://www.youtube.com/watch?v=abc123",
    "duration": 200,
    "thumbnails": [{"url": "https://i.ytimg.com/vi/abc123/hqdefault.jpg"}],
    "is_live": False,
}

MOCK_LIVESTREAM_RESULT = {
    "id": "live123",
    "title": "24/7 Lofi",
    "uploader": "Lofi Girl",
    "webpage_url": "https://www.youtube.com/watch?v=live123",
    "duration": None,
    "is_live": True,
    "thumbnails": [],
}

MOCK_PLAYLIST_RESULT = {
    "entries": [
        {"id": f"vid{i}", "title": f"Song {i}", "url": f"https://youtube.com/watch?v=vid{i}",
         "duration": 180, "thumbnails": []}
        for i in range(60)
    ]
}


class TestSearch:
    def test_search_returns_results(self, yt_service):
        with patch.object(yt_service, "_extract", return_value=MOCK_SEARCH_RESULT):
            results = yt_service.search("test query")
        assert len(results) == 2
        assert results[0]["video_id"] == "abc123"
        assert results[0]["title"] == "Test Song - Test Artist"
        assert results[0]["duration"] == 200

    def test_search_respects_count(self, yt_service):
        with patch.object(yt_service, "_extract", return_value=MOCK_SEARCH_RESULT):
            results = yt_service.search("test", count=1)
        assert len(results) == 1


class TestExtract:
    def test_extract_returns_track_data(self, yt_service):
        with patch.object(yt_service, "_extract", return_value=MOCK_EXTRACT_RESULT):
            data = yt_service.extract("https://youtube.com/watch?v=abc123")
        assert data["video_id"] == "abc123"
        assert data["title"] == "Test Song"
        assert data["artist"] == "Test Artist"
        assert data["duration"] == 200

    def test_extract_livestream_raises(self, yt_service):
        with patch.object(yt_service, "_extract", return_value=MOCK_LIVESTREAM_RESULT):
            with pytest.raises(ValueError, match="[Ll]ivestream"):
                yt_service.extract("https://youtube.com/watch?v=live123")

    def test_extract_too_long_raises(self, yt_service):
        long_video = {**MOCK_EXTRACT_RESULT, "duration": 1200}
        with patch.object(yt_service, "_extract", return_value=long_video):
            with pytest.raises(ValueError, match="[Dd]uration|[Ll]ong"):
                yt_service.extract("https://youtube.com/watch?v=abc123")

    def test_extract_falls_back_to_uploader(self, yt_service):
        no_artist = {**MOCK_EXTRACT_RESULT, "artist": None}
        with patch.object(yt_service, "_extract", return_value=no_artist):
            data = yt_service.extract("https://youtube.com/watch?v=abc123")
        assert data["artist"] == "Test Artist"  # falls back to uploader


class TestPlaylist:
    def test_playlist_truncates_to_max(self, yt_service):
        with patch.object(yt_service, "_extract", return_value=MOCK_PLAYLIST_RESULT):
            results = yt_service.extract_playlist("https://youtube.com/playlist?list=PL123")
        assert len(results) == 50  # MAX_PLAYLIST_IMPORT from config


class TestIsUrl:
    def test_youtube_url(self, yt_service):
        assert yt_service.is_url("https://www.youtube.com/watch?v=abc123") is True

    def test_youtu_be_url(self, yt_service):
        assert yt_service.is_url("https://youtu.be/abc123") is True

    def test_search_query(self, yt_service):
        assert yt_service.is_url("blinding lights the weeknd") is False

    def test_http_generic(self, yt_service):
        assert yt_service.is_url("http://example.com") is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_youtube.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'services.youtube'`

- [ ] **Step 3: Implement `services/youtube.py`**

```python
"""yt-dlp wrapper for YouTube search, metadata extraction, and download."""

from __future__ import annotations

import asyncio
import functools
import re
from pathlib import Path

from yt_dlp import YoutubeDL

import config
from utils.logger import log

_URL_PATTERN = re.compile(r"^https?://")

SEARCH_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": True,
    "skip_download": True,
}

EXTRACT_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "skip_download": True,
}

DOWNLOAD_OPTS = {
    "format": "bestaudio/best",
    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "opus",
            "preferredquality": config.AUDIO_QUALITY,
        }
    ],
    "outtmpl": str(config.AUDIO_CACHE_DIR / "%(id)s.%(ext)s"),
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
}


class YouTubeService:
    """Wraps yt-dlp for search, extract, and download operations."""

    def is_url(self, query: str) -> bool:
        """Check if the query is a URL rather than a search term."""
        return bool(_URL_PATTERN.match(query.strip()))

    def _extract(self, query: str, opts: dict | None = None) -> dict:
        """Synchronous yt-dlp extract_info call."""
        with YoutubeDL(opts or EXTRACT_OPTS) as ydl:
            return ydl.extract_info(query, download=False)

    def search(self, query: str, count: int | None = None) -> list[dict]:
        """Search YouTube and return lightweight result dicts.

        Returns list of {video_id, title, url, duration, thumbnail}.
        """
        if count is None:
            count = config.SEARCH_RESULTS_COUNT

        opts = {**SEARCH_OPTS, "default_search": f"ytsearch{count}"}
        data = self._extract(query, opts)

        entries = data.get("entries", [])
        results = []
        for entry in entries[:count]:
            thumbnails = entry.get("thumbnails") or []
            thumbnail = thumbnails[0]["url"] if thumbnails else None
            results.append(
                {
                    "video_id": entry.get("id", ""),
                    "title": entry.get("title", "Unknown"),
                    "url": entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                    "duration": entry.get("duration"),
                    "thumbnail": thumbnail,
                }
            )
        return results

    def extract(self, url: str) -> dict:
        """Full metadata extraction for a single video.

        Returns dict with {video_id, title, artist, url, duration, thumbnail}.
        Raises ValueError for livestreams or videos exceeding duration cap.
        """
        data = self._extract(url)

        duration = data.get("duration")
        if duration is None or data.get("is_live"):
            raise ValueError("Livestream URLs are not supported")
        if duration > config.MAX_SONG_DURATION_SECONDS:
            raise ValueError(
                f"Duration {duration}s exceeds max of {config.MAX_SONG_DURATION_SECONDS}s"
            )

        artist = data.get("artist") or data.get("uploader") or None
        thumbnails = data.get("thumbnails") or []
        thumbnail = thumbnails[-1]["url"] if thumbnails else None

        return {
            "video_id": data["id"],
            "title": data.get("title", "Unknown"),
            "artist": artist,
            "url": data.get("webpage_url", url),
            "duration": duration,
            "thumbnail": thumbnail,
        }

    def extract_playlist(self, url: str) -> list[dict]:
        """Extract entries from a playlist URL. Truncates to MAX_PLAYLIST_IMPORT."""
        opts = {**SEARCH_OPTS, "noplaylist": False}
        data = self._extract(url, opts)
        entries = data.get("entries", [])

        results = []
        for entry in entries[: config.MAX_PLAYLIST_IMPORT]:
            thumbnails = entry.get("thumbnails") or []
            thumbnail = thumbnails[0]["url"] if thumbnails else None
            results.append(
                {
                    "video_id": entry.get("id", ""),
                    "title": entry.get("title", "Unknown"),
                    "url": entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                    "duration": entry.get("duration"),
                    "thumbnail": thumbnail,
                }
            )
        return results

    def download(self, video_id: str, url: str) -> Path | None:
        """Download audio to cache. Returns file path or None on failure."""
        cached = config.AUDIO_CACHE_DIR / f"{video_id}.opus"
        if cached.exists():
            return cached

        try:
            with YoutubeDL(DOWNLOAD_OPTS) as ydl:
                ydl.download([url])
            if cached.exists():
                log.info(f"Downloaded {video_id} to cache")
                return cached
            return None
        except Exception as e:
            log.error(f"Download failed for {video_id}: {e}")
            return None

    async def async_search(self, query: str, count: int | None = None) -> list[dict]:
        """Run search in a thread pool to avoid blocking the event loop."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, functools.partial(self.search, query, count))

    async def async_extract(self, url: str) -> dict:
        """Run extract in a thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.extract, url)

    async def async_download(self, video_id: str, url: str) -> Path | None:
        """Run download in a thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.download, video_id, url)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_youtube.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/__init__.py services/youtube.py tests/test_youtube.py
git commit -m "feat: add YouTubeService with search, extract, download, and playlist support"
```

---

### Task 8: Audio Service + Tests

**Files:**
- Create: `services/audio.py`
- Create: `tests/test_audio.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_audio.py`:

```python
"""Tests for AudioService cache logic."""

import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from services.audio import AudioService


@pytest.fixture
def tmp_cache(tmp_path):
    """Create a temporary cache directory."""
    return tmp_path


@pytest.fixture
def audio_service(tmp_cache):
    yt_service = MagicMock()
    service = AudioService(youtube_service=yt_service, cache_dir=tmp_cache)
    return service


class TestCacheLookup:
    def test_cache_path(self, audio_service, tmp_cache):
        path = audio_service.cache_path("abc123")
        assert path == tmp_cache / "abc123.opus"

    def test_is_cached_true(self, audio_service, tmp_cache):
        (tmp_cache / "abc123.opus").write_bytes(b"fake audio")
        assert audio_service.is_cached("abc123") is True

    def test_is_cached_false(self, audio_service):
        assert audio_service.is_cached("nonexistent") is False


class TestCacheCleanup:
    def test_cleanup_removes_oldest(self, audio_service, tmp_cache):
        # Create files that exceed the max size
        for i in range(5):
            f = tmp_cache / f"vid{i}.opus"
            f.write_bytes(b"x" * (500 * 1024 * 1024))  # 500MB each = 2.5GB total

        # Access the newest ones to update access time
        for i in [3, 4]:
            os.utime(tmp_cache / f"vid{i}.opus", None)

        audio_service.max_cache_mb = 2048
        audio_service.cleanup_cache()

        remaining = list(tmp_cache.glob("*.opus"))
        total_size = sum(f.stat().st_size for f in remaining)
        assert total_size <= 2048 * 1024 * 1024

    def test_cleanup_noop_under_limit(self, audio_service, tmp_cache):
        (tmp_cache / "small.opus").write_bytes(b"x" * 1024)
        audio_service.max_cache_mb = 2048
        audio_service.cleanup_cache()
        assert (tmp_cache / "small.opus").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_audio.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'services.audio'`

- [ ] **Step 3: Implement `services/audio.py`**

```python
"""FFmpeg audio source management and cache cleanup."""

from __future__ import annotations

import os
from pathlib import Path

import discord

import config
from models.queue import Track
from utils.logger import log

# FFmpeg options for stream fallback (non-opus sources)
FFMPEG_STREAM_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class AudioService:
    """Manages FFmpeg audio sources and the download cache."""

    def __init__(
        self,
        youtube_service,
        cache_dir: Path | None = None,
        max_cache_mb: int | None = None,
    ) -> None:
        self.youtube_service = youtube_service
        self.cache_dir = cache_dir or config.AUDIO_CACHE_DIR
        self.max_cache_mb = max_cache_mb or config.AUDIO_CACHE_MAX_MB
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def cache_path(self, video_id: str) -> Path:
        """Return the cache file path for a video ID."""
        return self.cache_dir / f"{video_id}.opus"

    def is_cached(self, video_id: str) -> bool:
        """Check if a video's audio is in the cache."""
        return self.cache_path(video_id).exists()

    async def get_source(self, track: Track) -> discord.AudioSource:
        """Get a playable audio source for a track.

        Priority: cached opus file → download to cache → stream fallback.
        """
        cached = self.cache_path(track.video_id)

        # 1. Cache hit — opus passthrough
        if cached.exists():
            log.info(f"Cache hit for {track.video_id}")
            return discord.FFmpegOpusAudio(str(cached))

        # 2. Try downloading to cache
        path = await self.youtube_service.async_download(track.video_id, track.url)
        if path and path.exists():
            return discord.FFmpegOpusAudio(str(path))

        # 3. Stream fallback — re-extract for fresh URL
        log.warning(f"Download failed for {track.video_id}, falling back to stream")
        data = await self.youtube_service.async_extract(track.url)
        stream_url = data.get("url") or track.url
        return discord.FFmpegPCMAudio(stream_url, **FFMPEG_STREAM_OPTS)

    def cleanup_cache(self) -> None:
        """Delete oldest cached files if total cache exceeds max size."""
        files = list(self.cache_dir.glob("*.opus"))
        if not files:
            return

        total_bytes = sum(f.stat().st_size for f in files)
        max_bytes = self.max_cache_mb * 1024 * 1024

        if total_bytes <= max_bytes:
            return

        # Sort by last access time (oldest first)
        files.sort(key=lambda f: f.stat().st_atime)

        for f in files:
            if total_bytes <= max_bytes:
                break
            size = f.stat().st_size
            f.unlink()
            total_bytes -= size
            log.info(f"Cache cleanup: deleted {f.name} ({size // 1024}KB)")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_audio.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/audio.py tests/test_audio.py
git commit -m "feat: add AudioService with cache management and FFmpeg source resolution"
```

---

### Task 9: Embed Builders

**Files:**
- Create: `utils/embeds.py`

- [ ] **Step 1: Create `utils/embeds.py`**

```python
"""Discord embed builders for music bot responses."""

from __future__ import annotations

import discord

from models.queue import Track, LoopMode, MusicQueue
from utils.formatters import format_duration, progress_bar

# Brand colors
COLOR_NOW_PLAYING = 0x2C76DD   # blue
COLOR_QUEUED = 0xDF1141        # red
COLOR_SUCCESS = 0x0EAA51       # green
COLOR_ERROR = 0x7D3243         # dark pink
COLOR_QUEUE_LIST = 0x40EC88    # light green


def now_playing(track: Track, queue: MusicQueue, elapsed: int = 0) -> discord.Embed:
    """Build the 'Now Playing' embed for the current track."""
    title_str = track.title
    if track.artist:
        title_str = f"{track.title} — {track.artist}"

    embed = discord.Embed(
        title="Now Playing",
        description=f"[{title_str}]({track.url})",
        color=COLOR_NOW_PLAYING,
    )

    bar = progress_bar(elapsed, track.duration_seconds)
    embed.add_field(name="Duration", value=bar, inline=False)
    embed.add_field(name="Requested by", value=f"<@{track.requested_by}>", inline=True)
    embed.add_field(name="Loop", value=queue.loop_mode.value.capitalize(), inline=True)

    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)

    return embed


def song_queued(track: Track, position: int) -> discord.Embed:
    """Build the 'Song added to queue' embed."""
    title_str = track.title
    if track.artist:
        title_str = f"{track.title} — {track.artist}"

    embed = discord.Embed(
        title=f"Added to Queue (#{position})",
        description=f"[{title_str}]({track.url})",
        color=COLOR_QUEUED,
    )
    embed.add_field(name="Duration", value=format_duration(track.duration_seconds), inline=True)

    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)

    return embed


def queue_list(queue: MusicQueue, page: int = 0, per_page: int = 10) -> discord.Embed:
    """Build a paginated queue list embed."""
    current = queue.get_current()
    total = len(queue.tracks)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages - 1)

    embed = discord.Embed(
        title=f"Queue ({total} tracks)",
        color=COLOR_QUEUE_LIST,
    )

    if current:
        title_str = current.title
        if current.artist:
            title_str = f"{current.title} — {current.artist}"
        embed.add_field(
            name="Now Playing",
            value=f"[{title_str}]({current.url}) [{format_duration(current.duration_seconds)}]",
            inline=False,
        )

    start = page * per_page
    end = min(start + per_page, total)
    lines = []
    for i in range(start, end):
        track = queue.tracks[i]
        marker = "▶ " if i == queue.current_index else ""
        lines.append(
            f"`{i + 1}.` {marker}**{track.title}** [{format_duration(track.duration_seconds)}]"
        )

    if lines:
        embed.add_field(name="Tracks", value="\n".join(lines), inline=False)

    embed.set_footer(text=f"Page {page + 1}/{total_pages}")
    return embed


def error(message: str) -> discord.Embed:
    """Build an error embed."""
    return discord.Embed(
        title="Error",
        description=message,
        color=COLOR_ERROR,
    )
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
python -c "from utils.embeds import now_playing, song_queued, queue_list, error; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add utils/embeds.py
git commit -m "feat: add Discord embed builders for now playing, queue, and errors"
```

---

### Task 10: Help Cog

**Files:**
- Create: `cogs/__init__.py`
- Create: `cogs/help.py`

- [ ] **Step 1: Create `cogs/__init__.py`**

Empty file:

```python
```

- [ ] **Step 2: Create `cogs/help.py`**

```python
"""Help slash command."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

COMMANDS_INFO = [
    ("/play <query or URL>", "Search YouTube or queue a URL directly"),
    ("/skip", "Skip to the next song"),
    ("/pause", "Pause the current song"),
    ("/resume", "Resume playback"),
    ("/stop", "Stop playback, clear queue, and leave voice"),
    ("/queue", "Show the current queue"),
    ("/shuffle", "Shuffle upcoming songs in the queue"),
    ("/loop <off|single|queue>", "Set loop mode"),
    ("/nowplaying", "Show what's currently playing"),
    ("/replay", "Restart the current song from the beginning"),
    ("/help", "Show this help message"),
]


class HelpCog(commands.Cog):
    """Provides the /help command."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="Show all available commands")
    @app_commands.checks.cooldown(1, 5.0)
    async def help_command(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Dexter — Commands",
            description="Here's what I can do.",
            color=0x2C76DD,
        )

        lines = []
        for cmd, desc in COMMANDS_INFO:
            lines.append(f"**`{cmd}`** — {desc}")

        embed.add_field(name="Commands", value="\n".join(lines), inline=False)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
```

- [ ] **Step 3: Commit**

```bash
git add cogs/__init__.py cogs/help.py
git commit -m "feat: add /help slash command cog"
```

---

### Task 11: Music Cog — Core Playback

**Files:**
- Create: `cogs/music.py`

This is the largest task. It implements `/play`, `/skip`, `/pause`, `/resume`, `/stop`, and the playback engine (play_next, after-callback, voice join logic).

- [ ] **Step 1: Create `cogs/music.py` with play, skip, pause, resume, stop**

```python
"""Music slash commands and playback engine."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

import config
from models.queue import Track, LoopMode, MusicQueue
from utils import embeds
from utils.logger import log

if TYPE_CHECKING:
    from services.youtube import YouTubeService
    from services.audio import AudioService


class SongSelect(discord.ui.Select):
    """Dropdown menu for selecting a song from search results."""

    def __init__(self, results: list[dict], cog: "MusicCog") -> None:
        self.results = results
        self.cog = cog
        options = []
        for i, r in enumerate(results):
            duration = r.get("duration")
            desc = f"Duration: {duration // 60}:{duration % 60:02d}" if duration else "Unknown duration"
            options.append(
                discord.SelectOption(
                    label=r["title"][:100],
                    description=desc[:100],
                    value=str(i),
                )
            )
        super().__init__(placeholder="Pick a song...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        index = int(self.values[0])
        selected = self.results[index]
        await self.cog._queue_from_selection(interaction, selected)
        self.view.stop()


class SongSelectView(discord.ui.View):
    """View containing the song select dropdown."""

    def __init__(self, results: list[dict], cog: "MusicCog", timeout: float = 180.0) -> None:
        super().__init__(timeout=timeout)
        self.add_item(SongSelect(results, cog))

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True


class QueuePageView(discord.ui.View):
    """Paginated queue view with Previous/Next buttons."""

    def __init__(self, queue: MusicQueue, timeout: float = 120.0) -> None:
        super().__init__(timeout=timeout)
        self.queue = queue
        self.page = 0

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = max(0, self.page - 1)
        embed = embeds.queue_list(self.queue, page=self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        total_pages = max(1, (len(self.queue.tracks) + 9) // 10)
        self.page = min(total_pages - 1, self.page + 1)
        embed = embeds.queue_list(self.queue, page=self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True


class MusicCog(commands.Cog):
    """All music slash commands and the playback engine."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.queues: dict[int, MusicQueue] = {}

    @property
    def youtube(self) -> "YouTubeService":
        return self.bot.youtube_service

    @property
    def audio(self) -> "AudioService":
        return self.bot.audio_service

    @property
    def db(self):
        return self.bot.db

    def get_queue(self, guild_id: int) -> MusicQueue:
        """Get or create the MusicQueue for a guild."""
        if guild_id not in self.queues:
            self.queues[guild_id] = MusicQueue(guild_id)
        return self.queues[guild_id]

    async def _ensure_voice(self, interaction: discord.Interaction) -> discord.VoiceClient | None:
        """Ensure bot is in the user's voice channel. Returns VoiceClient or None."""
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send(embed=embeds.error("You're not in a voice channel."))
            return None

        user_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            voice_client = await user_channel.connect()
        return voice_client

    async def _play_track(self, guild: discord.Guild, track: Track) -> None:
        """Start playing a track through the voice client."""
        voice_client = guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return

        queue = self.get_queue(guild.id)
        queue.is_playing = True
        queue.is_paused = False

        source = await self.audio.get_source(track)

        def after_callback(error):
            if error:
                log.error(f"Playback error in guild {guild.id}: {error}")
            asyncio.run_coroutine_threadsafe(
                self._on_track_end(guild), self.bot.loop
            )

        if voice_client.is_playing():
            voice_client.stop()

        voice_client.play(source, after=after_callback)
        log.info(f"Playing '{track.title}' in guild {guild.id}")

    async def _on_track_end(self, guild: discord.Guild) -> None:
        """Called when a track finishes naturally. Handles advance/loop logic."""
        queue = self.get_queue(guild.id)

        next_track = queue.advance()
        if next_track:
            await self._play_track(guild, next_track)
            # Update now playing embed
            channel = self._get_text_channel(guild)
            if channel:
                embed = embeds.now_playing(next_track, queue)
                await channel.send(embed=embed)
        else:
            queue.is_playing = False

    def _get_text_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """Get a text channel to post messages in."""
        if guild.system_channel:
            return guild.system_channel
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                return channel
        return None

    async def _queue_from_selection(self, interaction: discord.Interaction, selected: dict) -> None:
        """Queue a song after the user picks from the select menu."""
        await interaction.response.defer()

        try:
            data = await self.youtube.async_extract(selected["url"])
        except ValueError as e:
            await interaction.followup.send(embed=embeds.error(str(e)))
            return

        track = Track(
            video_id=data["video_id"],
            title=data["title"],
            artist=data["artist"],
            url=data["url"],
            duration_seconds=data["duration"],
            requested_by=interaction.user.id,
            thumbnail=data.get("thumbnail"),
        )

        queue = self.get_queue(interaction.guild.id)
        position = queue.add(track) + 1

        # Log to database
        await self._log_track(interaction, track)

        voice_client = await self._ensure_voice(interaction)
        if not voice_client:
            return

        if not queue.is_playing:
            queue.current_index = len(queue.tracks) - 1
            await self._play_track(interaction.guild, track)
            embed = embeds.now_playing(track, queue)
            await interaction.followup.send(embed=embed)
        else:
            embed = embeds.song_queued(track, position)
            await interaction.followup.send(embed=embed)

    async def _log_track(self, interaction: discord.Interaction, track: Track) -> None:
        """Log a queued track to all database tables."""
        from database import log_song, update_artist_count, update_user_profile, increment_daily_stat

        await log_song(
            self.db,
            guild_id=str(interaction.guild.id),
            user_id=str(interaction.user.id),
            title=track.title,
            artist=track.artist,
            url=track.url,
            duration=track.duration_seconds,
        )
        await update_artist_count(self.db, user_id=str(interaction.user.id), artist=track.artist)
        await update_user_profile(self.db, user_id=str(interaction.user.id), username=interaction.user.display_name)
        await increment_daily_stat(self.db, "total_songs_played")
        await increment_daily_stat(self.db, "total_commands")

    # ──────────────────────────── SLASH COMMANDS ────────────────────────────

    @app_commands.command(name="play", description="Search YouTube or queue a URL")
    @app_commands.describe(query="Song name or YouTube URL")
    @app_commands.checks.cooldown(1, config.PLAY_COOLDOWN_SECONDS)
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message(
                embed=embeds.error("You're not in a voice channel."), ephemeral=True
            )

        await interaction.response.defer()

        if self.youtube.is_url(query):
            # Direct URL — skip search menu
            try:
                # Check for playlist
                if "list=" in query:
                    results = await self.youtube.async_search(query, count=1)
                    if not results:
                        playlist_results = self.youtube.extract_playlist(query)
                        if playlist_results:
                            count = 0
                            for item in playlist_results:
                                try:
                                    await self._queue_from_result(interaction, item)
                                    count += 1
                                except Exception:
                                    continue
                            await interaction.followup.send(f"Queued {count} tracks from playlist.")
                            return

                data = await self.youtube.async_extract(query)
            except ValueError as e:
                return await interaction.followup.send(embed=embeds.error(str(e)))

            track = Track(
                video_id=data["video_id"],
                title=data["title"],
                artist=data["artist"],
                url=data["url"],
                duration_seconds=data["duration"],
                requested_by=interaction.user.id,
                thumbnail=data.get("thumbnail"),
            )

            queue = self.get_queue(interaction.guild.id)
            position = queue.add(track) + 1

            await self._log_track(interaction, track)

            voice_client = await self._ensure_voice(interaction)
            if not voice_client:
                return

            if not queue.is_playing:
                queue.current_index = len(queue.tracks) - 1
                await self._play_track(interaction.guild, track)
                embed = embeds.now_playing(track, queue)
                await interaction.followup.send(embed=embed)
            else:
                embed = embeds.song_queued(track, position)
                await interaction.followup.send(embed=embed)
        else:
            # Text search — show select menu
            results = await self.youtube.async_search(query)
            if not results:
                return await interaction.followup.send(embed=embeds.error("No results found."))

            view = SongSelectView(results, self)
            await interaction.followup.send("Pick a song:", view=view)

    @app_commands.command(name="skip", description="Skip to the next song")
    @app_commands.checks.cooldown(1, config.SKIP_COOLDOWN_SECONDS)
    async def skip(self, interaction: discord.Interaction) -> None:
        queue = self.get_queue(interaction.guild.id)
        voice_client = interaction.guild.voice_client

        if not voice_client or not queue.is_playing:
            return await interaction.response.send_message(
                embed=embeds.error("Nothing is playing."), ephemeral=True
            )

        next_track = queue.skip()
        if next_track:
            voice_client.stop()  # triggers after_callback, but we override
            await self._play_track(interaction.guild, next_track)
            embed = embeds.now_playing(next_track, queue)
            await interaction.response.send_message(embed=embed)
        else:
            voice_client.stop()
            queue.is_playing = False
            await interaction.response.send_message("End of queue.")

    @app_commands.command(name="pause", description="Pause the current song")
    async def pause(self, interaction: discord.Interaction) -> None:
        voice_client = interaction.guild.voice_client
        queue = self.get_queue(interaction.guild.id)

        if not voice_client or not voice_client.is_playing():
            return await interaction.response.send_message(
                embed=embeds.error("Nothing is playing."), ephemeral=True
            )

        voice_client.pause()
        queue.is_playing = False
        queue.is_paused = True
        await interaction.response.send_message("Paused.")

    @app_commands.command(name="resume", description="Resume playback")
    async def resume(self, interaction: discord.Interaction) -> None:
        voice_client = interaction.guild.voice_client
        queue = self.get_queue(interaction.guild.id)

        if not voice_client or not voice_client.is_paused():
            return await interaction.response.send_message(
                embed=embeds.error("Nothing is paused."), ephemeral=True
            )

        voice_client.resume()
        queue.is_playing = True
        queue.is_paused = False
        await interaction.response.send_message("Resumed.")

    @app_commands.command(name="stop", description="Stop playback, clear queue, leave voice")
    async def stop(self, interaction: discord.Interaction) -> None:
        voice_client = interaction.guild.voice_client
        queue = self.get_queue(interaction.guild.id)

        if voice_client:
            voice_client.stop()
            await voice_client.disconnect()

        queue.clear()
        await interaction.response.send_message("Stopped and cleared the queue.")

    @app_commands.command(name="queue", description="Show the current queue")
    @app_commands.checks.cooldown(1, 2.0)
    async def queue_cmd(self, interaction: discord.Interaction) -> None:
        queue = self.get_queue(interaction.guild.id)

        if not queue.tracks:
            return await interaction.response.send_message(
                embed=embeds.error("The queue is empty."), ephemeral=True
            )

        view = QueuePageView(queue)
        embed = embeds.queue_list(queue, page=0)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="shuffle", description="Shuffle upcoming songs")
    @app_commands.checks.cooldown(1, 2.0)
    async def shuffle(self, interaction: discord.Interaction) -> None:
        queue = self.get_queue(interaction.guild.id)

        if len(queue.upcoming()) == 0:
            return await interaction.response.send_message(
                embed=embeds.error("Nothing to shuffle."), ephemeral=True
            )

        queue.shuffle()
        await interaction.response.send_message(f"Shuffled {len(queue.upcoming())} upcoming tracks.")

    @app_commands.command(name="loop", description="Set loop mode")
    @app_commands.describe(mode="Loop mode")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Single", value="single"),
        app_commands.Choice(name="Queue", value="queue"),
    ])
    async def loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        queue = self.get_queue(interaction.guild.id)
        queue.loop_mode = LoopMode(mode.value)
        await interaction.response.send_message(f"Loop mode: **{mode.name}**")

    @app_commands.command(name="nowplaying", description="Show what's currently playing")
    @app_commands.checks.cooldown(1, 2.0)
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        queue = self.get_queue(interaction.guild.id)
        track = queue.get_current()

        if not track or not queue.is_playing:
            return await interaction.response.send_message(
                embed=embeds.error("Nothing is playing."), ephemeral=True
            )

        embed = embeds.now_playing(track, queue)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="replay", description="Restart the current song")
    @app_commands.checks.cooldown(1, 2.0)
    async def replay(self, interaction: discord.Interaction) -> None:
        queue = self.get_queue(interaction.guild.id)
        track = queue.get_current()
        voice_client = interaction.guild.voice_client

        if not track or not voice_client:
            return await interaction.response.send_message(
                embed=embeds.error("Nothing is playing."), ephemeral=True
            )

        await interaction.response.defer()
        voice_client.stop()
        await self._play_track(interaction.guild, track)
        embed = embeds.now_playing(track, queue)
        await interaction.followup.send(embed=embed)

    # ──────────────────────────── VOICE EVENTS ────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        """Handle bot disconnect recovery and empty channel detection."""
        if not member.guild.voice_client:
            return

        voice_client = member.guild.voice_client
        queue = self.get_queue(member.guild.id)

        # Bot was disconnected
        if member.id == self.bot.user.id and after.channel is None and before.channel is not None:
            log.warning(f"Bot disconnected from voice in guild {member.guild.id}")
            queue.is_playing = False
            queue.is_paused = False

            # Attempt reconnect
            for attempt in range(3):
                try:
                    await asyncio.sleep(1)
                    vc = await before.channel.connect()
                    track = queue.get_current()
                    if track:
                        await self._play_track(member.guild, track)
                        log.info(f"Reconnected and restarted track in guild {member.guild.id}")
                    return
                except Exception as e:
                    log.error(f"Reconnect attempt {attempt + 1} failed: {e}")

            queue.clear()
            channel = self._get_text_channel(member.guild)
            if channel:
                await channel.send(embed=embeds.error("Lost voice connection. Queue cleared."))
            return

        # Check if bot is now alone in voice
        if voice_client.channel and len(voice_client.channel.members) == 1:
            # Only the bot remains — idle timer will handle disconnect
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
python -c "from cogs.music import MusicCog; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add cogs/music.py
git commit -m "feat: add music cog with play, skip, pause, resume, stop, queue, shuffle, loop, nowplaying, replay"
```

---

### Task 12: Bot Entry Point

**Files:**
- Create: `bot.py`

- [ ] **Step 1: Create `bot.py`**

```python
"""Dexter Discord bot — entry point, service wiring, and background tasks."""

from __future__ import annotations

import argparse
import asyncio
import sys

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from database import init_db
from services.audio import AudioService
from services.youtube import YouTubeService
from utils.logger import log

# Load environment variables
from dotenv import load_dotenv
import os

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    log.error("DISCORD_TOKEN not set in .env")
    sys.exit(1)


def create_bot() -> commands.Bot:
    """Create and configure the bot instance."""
    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True
    intents.guilds = True
    intents.members = True

    bot = commands.Bot(
        command_prefix="!",  # unused but required by commands.Bot
        intents=intents,
        activity=discord.Activity(
            type=discord.ActivityType.listening, name="music"
        ),
    )

    return bot


bot = create_bot()


# ──────────────────────────── SERVICE WIRING ────────────────────────────


@bot.event
async def on_ready():
    """Initialize services, database, and cogs once the bot is connected."""
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")

    # Database
    bot.db = await aiosqlite.connect(config.BASE_DIR / "data" / "dexter.db")
    bot.db.row_factory = aiosqlite.Row
    await init_db(bot.db)

    # Services
    bot.youtube_service = YouTubeService()
    bot.audio_service = AudioService(youtube_service=bot.youtube_service)

    # Load cogs
    await bot.load_extension("cogs.music")
    await bot.load_extension("cogs.help")

    # Start background tasks
    if not idle_check.is_running():
        idle_check.start()
    if not cache_cleanup.is_running():
        cache_cleanup.start()

    log.info("Dexter is ready.")


@bot.event
async def on_close():
    """Clean up resources on shutdown."""
    if hasattr(bot, "db"):
        await bot.db.close()


# ──────────────────────────── OWNER COMMANDS ────────────────────────────


@bot.tree.command(name="sync", description="Sync slash commands (owner only)")
@app_commands.describe(guild_id="Guild ID to sync to (omit for global)")
async def sync_commands(interaction: discord.Interaction, guild_id: str | None = None):
    if interaction.user.id != bot.owner_id:
        return await interaction.response.send_message("Not authorized.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    if guild_id:
        guild = discord.Object(id=int(guild_id))
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        await interaction.followup.send(f"Synced {len(synced)} commands to guild {guild_id}.")
    else:
        synced = await bot.tree.sync()
        await interaction.followup.send(f"Synced {len(synced)} commands globally.")

    log.info(f"Synced {len(synced)} commands ({'guild ' + guild_id if guild_id else 'global'})")


# ──────────────────────────── BACKGROUND TASKS ────────────────────────────


@tasks.loop(seconds=60)
async def idle_check():
    """Check for idle voice connections and disconnect after timeout."""
    for vc in bot.voice_clients:
        guild = vc.guild
        music_cog = bot.cogs.get("MusicCog")
        if not music_cog:
            continue

        queue = music_cog.get_queue(guild.id)

        # Count human members in the channel
        human_members = [m for m in vc.channel.members if not m.bot]

        if len(human_members) == 0:
            # Bot is alone
            if not hasattr(vc, "_idle_seconds"):
                vc._idle_seconds = 0
            vc._idle_seconds += 60

            if vc._idle_seconds >= config.IDLE_TIMEOUT_SECONDS:
                log.info(f"Idle timeout in guild {guild.id}, disconnecting")
                vc.stop()
                await vc.disconnect()
                queue.clear()

                channel = music_cog._get_text_channel(guild)
                if channel:
                    await channel.send("Left the voice channel after being alone for too long.")
        else:
            if hasattr(vc, "_idle_seconds"):
                vc._idle_seconds = 0


@idle_check.before_loop
async def before_idle_check():
    await bot.wait_until_ready()


@tasks.loop(hours=1)
async def cache_cleanup():
    """Hourly cache size check and cleanup."""
    if hasattr(bot, "audio_service"):
        bot.audio_service.cleanup_cache()
        log.info("Cache cleanup check completed")


@cache_cleanup.before_loop
async def before_cache_cleanup():
    await bot.wait_until_ready()


# ──────────────────────────── FIRST-RUN & MAIN ────────────────────────────


async def first_run(guild_id: str | None = None):
    """Sync commands and exit. Used for initial slash command registration."""

    @bot.event
    async def on_ready():
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            log.info(f"First-run: synced {len(synced)} commands to guild {guild_id}")
        else:
            synced = await bot.tree.sync()
            log.info(f"First-run: synced {len(synced)} commands globally")

        await bot.close()

    # Load cogs so their commands are registered before sync
    await bot.load_extension("cogs.music")
    await bot.load_extension("cogs.help")
    await bot.start(DISCORD_TOKEN)


def main():
    parser = argparse.ArgumentParser(description="Dexter Discord Bot")
    parser.add_argument("--first-run", action="store_true", help="Sync commands and exit")
    parser.add_argument("--guild", type=str, help="Guild ID for dev sync")
    args = parser.parse_args()

    if args.first_run:
        asyncio.run(first_run(args.guild))
    else:
        bot.run(DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it parses cleanly**

```bash
python -c "import bot; print('OK')"
```

Expected: `OK` (will warn about missing DISCORD_TOKEN if .env isn't set up yet, but won't crash on import).

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "feat: add bot entry point with service wiring, background tasks, and first-run sync"
```

---

### Task 13: Environment Setup & First Boot Test

This task requires the user to have their Discord bot token ready.

- [ ] **Step 1: Create `.env` from template**

```bash
cp .env.example .env
```

Then edit `.env` and add your `DISCORD_TOKEN`.

- [ ] **Step 2: Verify FFmpeg is on PATH**

```bash
ffmpeg -version
```

Expected: FFmpeg version info printed. If not found, add FFmpeg to PATH.

- [ ] **Step 3: Verify Python version**

```bash
python --version
```

Expected: Python 3.11 or higher.

- [ ] **Step 4: Run all automated tests**

```bash
python -m pytest tests/ -v
```

Expected: All tests pass (formatters, queue, database, youtube, audio).

- [ ] **Step 5: First-run sync to test guild**

```bash
python bot.py --first-run --guild YOUR_GUILD_ID
```

Expected: Bot logs in, syncs commands to the specified guild, then exits. Slash commands should appear in Discord within seconds.

- [ ] **Step 6: Normal boot**

```bash
python bot.py
```

Expected: Bot comes online, shows "Listening to music" status. Slash commands are visible in the test server.

- [ ] **Step 7: Smoke test**

In Discord:
1. Join a voice channel
2. Run `/play never gonna give you up`
3. Verify: select menu appears with 5 results
4. Pick a song
5. Verify: bot joins voice, music plays, "Now Playing" embed appears
6. Run `/skip` — verifies skip works
7. Run `/stop` — bot leaves, queue cleared

- [ ] **Step 8: Commit any adjustments**

```bash
git add -A
git commit -m "feat: environment setup and first successful boot verified"
```

---

## Self-Review Checklist

- **Spec coverage:**
  - [x] Project scaffolding (Task 1)
  - [x] Config module (Task 2)
  - [x] Logger (Task 3)
  - [x] Formatters + tests (Task 4)
  - [x] Queue model + tests (Task 5)
  - [x] Database + tests (Task 6)
  - [x] YouTube service + tests (Task 7)
  - [x] Audio service + tests (Task 8)
  - [x] Embeds (Task 9)
  - [x] Help cog (Task 10)
  - [x] Music cog — all slash commands (Task 11)
  - [x] Bot entry point, wiring, background tasks, first-run sync (Task 12)
  - [x] Environment setup + smoke test (Task 13)
  - [x] Edge cases: disconnect recovery (Task 11 voice events), idle auto-leave (Task 12 idle_check), duration/livestream rejection (Task 7 extract), cache cleanup (Task 8/12)

- **Placeholder scan:** No TBDs, TODOs, or "implement later" found.

- **Type consistency:** `Track`, `LoopMode`, `MusicQueue` — names consistent across models, services, cogs, embeds, and tests. Method names (`skip()`, `advance()`, `shuffle()`, `clear()`, `get_current()`) consistent throughout.
