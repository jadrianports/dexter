# Coding Conventions

**Analysis Date:** 2026-06-01

## Naming Patterns

**Files:**
- Lowercase with underscores: `music.py`, `message_buffer.py`, `user_profile.py`
- Descriptive module names that reflect the primary class or function set
- Test files prefixed with `test_`: `test_queue.py`, `test_youtube.py`, `test_database.py`

**Functions:**
- Lowercase with underscores: `format_duration()`, `update_artist_count()`, `get_user_summary()`
- Private methods prefixed with underscore: `_extract()`, `_ensure_voice()`, `_advance()`
- Async functions use same convention: `async def get_recent_songs()`
- Helper functions use descriptive names: `make_track()` in tests, `setup_logger()` in utils

**Variables:**
- Lowercase with underscores: `guild_id`, `user_profile`, `voice_client`
- Constants in SCREAMING_SNAKE_CASE: `MAX_SONG_DURATION_SECONDS`, `AUDIO_CACHE_DIR`, `COLOR_NOW_PLAYING`
- Private module-level variables: `_URL_PATTERN`, `_idle_seconds`
- Discord object IDs typically as type-hinted strings or ints: `guild_id: int`, `user_id: str`

**Types:**
- Union syntax via `|`: `Track | None`, `str | None`, `dict[int, MusicQueue]`
- Dataclass usage for models: `@dataclass Track`, `@dataclass class LoopMode(Enum)`
- Enum classes: `class LoopMode(Enum):` with `.OFF`, `.SINGLE`, `.QUEUE` values
- Type hints on all function signatures: always include return type

**Classes:**
- PascalCase: `MusicQueue`, `YouTubeService`, `MessageBuffer`, `SongSelect`
- Discord UI classes inherit from discord base: `SongSelect(discord.ui.Select)`, `QueuePageView(discord.ui.View)`
- Cogs inherit from `commands.Cog`: `class MusicCog(commands.Cog):`

## Code Style

**Formatting:**
- No explicit formatter configured (no `.prettierrc`, `.pylintrc`, or `black` config found)
- Implicit style observed:
  - 4-space indentation
  - Line length approximately 100-120 characters (not strictly enforced)
  - Trailing commas in multi-line dicts/lists
  - Double quotes for strings (not single quotes)

**Linting:**
- No linter config file present
- pytest is available (in `requirements.txt`)
- Code follows common Python conventions without strict enforcement

**Docstring Style:**
- Module-level docstrings at the top of every file: `"""Purpose of this module."""`
- Function docstrings use triple quotes with description and optional Returns/Raises:
  ```python
  def format_duration(seconds: int) -> str:
      """Format seconds into H:MM:SS or M:SS string."""
  ```
- Optional multi-line docstrings with parameter descriptions when needed:
  ```python
  async def _play_track(self, guild: discord.Guild, track: Track, _skipped: list | None = None) -> None:
      """Start playing a track through the voice client.

      Silently skips unavailable tracks, posting one summary message.
      """
  ```

## Import Organization

**Order:**
1. `from __future__ import annotations` (always first)
2. Standard library imports (`asyncio`, `json`, `logging`, `re`, `sys`, etc.)
3. Third-party imports (`discord`, `aiosqlite`, `yt_dlp`, `pytest`)
4. Local imports (relative to project: `config`, `database`, `models.*`, `services.*`, `utils.*`)
5. Conditional imports under `if TYPE_CHECKING:` for type hints only

**Path Aliases:**
- No path aliases configured
- All imports are absolute from project root: `from models.queue import Track`
- Type-only imports for avoiding circular dependencies: `if TYPE_CHECKING: from services.youtube import YouTubeService`

**Example from `cogs/music.py`:**
```python
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
```

## Error Handling

**Patterns:**
- Try/except blocks with specific exception types, never bare `except:`
- Logging errors with `log.error()` including traceback: `log.error(f"message", exc_info=True)`
- Custom exceptions for service-level errors: `GeminiAPIError`, `GeminiRateLimitError`
- Validation via `ValueError` for invalid input: `raise ValueError("Livestream URLs not supported")`
- Async error handlers in Discord commands use `interaction.response.is_done()` to prevent double-responses

**Example from `cogs/music.py`:**
```python
except Exception as e:
    log.error(f"Song select callback error: {e}", exc_info=True)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embeds.error(f"Something went wrong: {e}"))
        else:
            await interaction.response.send_message(embed=embeds.error(f"Something went wrong: {e}"))
    except Exception:
        pass
```

## Logging

**Framework:** Python's standard `logging` module

**Setup:** Configured in `utils/logger.py` via `setup_logger()` function
- File logger with daily rotation (midnight cutoff)
- Retention policy: 14 days by default (configured in `config.LOG_RETENTION_DAYS`)
- Log format: `[YYYY-MM-DD HH:MM:SS] [LEVEL] [module] message`
- Console output during development
- File output to `logs/dexter.log`

**Usage:**
- Global logger instance: `from utils.logger import log`
- Info level for normal operations: `log.info("Logged in as ...")`
- Error level with traceback: `log.error("failed", exc_info=True)`
- Warning level for non-critical issues: `log.warning("GEMINI_API_KEY not set")`

**Discord Error Logging:**
- Separate integration via `log_to_discord()` function in `utils/logger.py`
- Posts embeds to designated error channel (via `config.ERROR_LOG_CHANNEL_ID`)
- Only logs if channel ID is set (silently skipped otherwise)

## Comments

**When to Comment:**
- Inline comments explain **why** not **what**: "prevents stale after-callbacks from firing on skip"
- Comments for complex logic or non-obvious decisions
- URL/reference comments for external resources (e.g., yt-dlp quirks)
- Algorithm explanations in critical sections (e.g., queue index math)

**JSDoc/TSDoc:**
- Not used (Python project, not TypeScript)
- Function docstrings serve this purpose

**Example from `models/queue.py`:**
```python
def _advance(self, respect_single_loop: bool) -> Track | None:
    """Advance to next track (natural song end — respects SINGLE loop).

    Returns the next Track, or None if queue is exhausted.
    """
```

## Function Design

**Size:**
- Functions kept concise, typically 10-30 lines
- Longer functions decomposed into private helper methods (e.g., `_play_track()` calls `_advance()`)
- Discord command handlers use `defer()` immediately for long-running tasks

**Parameters:**
- Keyword-only parameters for clarity: `await db.execute(..., guild_id=..., user_id=...)`
- Type hints on every parameter: `def log_song(db: aiosqlite.Connection, *, guild_id: str, user_id: str)`
- Optional parameters via `| None`: `artist: str | None`
- Default values for optional config: `count: int | None = None` defaults to `config.SEARCH_RESULTS_COUNT`

**Return Values:**
- Always declare return type: `-> str | None`, `-> list[dict]`, `-> Track`
- None is explicit: `-> None` not omitted
- Optional returns documented in docstring

**Example from `database.py`:**
```python
async def update_user_profile(
    db: aiosqlite.Connection, *, user_id: str, username: str
) -> None:
    """Create or update a user profile, incrementing their song count."""
```

## Module Design

**Exports:**
- No `__all__` exports (implicit public API)
- Modules export all public names, private names prefixed with `_`
- Services expose methods as class methods, not module functions

**Barrel Files:**
- `models/__init__.py` empty (no re-exports)
- `services/__init__.py` empty
- Direct imports: `from models.queue import Track`

**Personality & Sarcasm:**
- Lowercase energy enforced: `"something broke and it wasn't my fault. probably."`
- No caps lock or excessive punctuation in user-facing strings
- One emoji max per message: used in personality responses
- References tracked user behavior in messages

**Example from `bot.py`:**
```python
await interaction.response.send_message(
    "something broke and it wasn't my fault. probably.",
    ephemeral=True,
)
```

---

*Convention analysis: 2026-06-01*
