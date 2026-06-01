# Testing Patterns

**Analysis Date:** 2026-06-01

## Test Framework

**Runner:**
- pytest 8.x+
- Config: No `pytest.ini` or `setup.cfg` found; uses implicit defaults
- Dependencies: `pytest`, `pytest-asyncio` (in `requirements.txt`)

**Assertion Library:**
- Python built-in `assert` statements (no additional library)
- pytest assertions with `==`, `is`, `in`, and `pytest.raises()`

**Run Commands:**
```bash
pytest                              # Run all tests
pytest -v                           # Verbose output with test names
pytest tests/test_queue.py          # Run single test file
pytest tests/test_queue.py::TestMusicQueueSkip  # Run single test class
pytest -k "test_skip"               # Run tests matching pattern
pytest --tb=short                   # Shorter traceback format
```

**No watch mode or coverage commands detected** (not configured).

## Test File Organization

**Location:**
- All tests in `tests/` directory at project root
- Co-located alongside source (tests are separate, not embedded in source modules)

**Naming:**
- Test files: `test_*.py` prefix
- Test classes: `Test*` prefix (e.g., `TestMusicQueueAdd`, `TestSchema`)
- Test methods: `test_*` prefix (e.g., `test_add_track`, `test_tables_created`)
- Fixtures: use `@pytest.fixture` decorator, named functionally (e.g., `db`, `yt_service`, `audio_service`)
- Async fixtures: use `@pytest_asyncio.fixture` for coroutine setup

**Structure:**
```
tests/
├── test_queue.py                   # Models: MusicQueue, Track, LoopMode
├── test_database.py                # Database schema and query helpers
├── test_database_phase2.py         # Phase 2 database features
├── test_youtube.py                 # YouTubeService search, extract, download
├── test_audio.py                   # AudioService cache logic
├── test_gemini.py                  # GeminiService mocking
├── test_message_buffer.py          # MessageBuffer rolling buffer
├── test_formatters.py              # Duration/progress bar formatting
├── test_prompts.py                 # Prompt builder functions
├── test_responses.py               # Personality responses
├── test_seasonal.py                # Seasonal context injection
├── test_server_state.py            # Per-server state tracking
├── test_user_profile.py            # User profile queries
├── test_rate_limiter.py            # Rate limiting logic
├── test_ai_helpers.py              # AI helper functions
└── __init__.py                     # Empty init file
```

## Test Structure

**Suite Organization:**
- Test classes group related test methods (one per major feature/function)
- Class names reflect what they test: `TestMusicQueueAdd`, `TestPlaylist`, `TestLogSong`
- No class inheritance; each test class is independent
- Setup/teardown via fixtures (not `setUp()`/`tearDown()` methods)

**Pattern from `tests/test_queue.py`:**
```python
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
```

**Patterns:**
- Helper functions (`make_track()`) create test data with sensible defaults
- Test methods are short (5-15 lines typical)
- One assertion per test (or tightly grouped related assertions)
- Test names describe the scenario: `test_skip_ignores_single_loop`, `test_advance_repeats_on_single_loop`

## Mocking

**Framework:** `unittest.mock` from Python standard library

**Imports:**
- `from unittest.mock import patch, MagicMock` for synchronous tests
- `from unittest.mock import AsyncMock, MagicMock, patch` for async tests

**Patterns:**

**Mocking methods on objects:**
```python
@pytest.fixture
def yt_service():
    return YouTubeService()

def test_search_returns_results(yt_service):
    with patch.object(yt_service, "_extract", return_value=MOCK_SEARCH_RESULT):
        results = yt_service.search("test query")
    assert len(results) == 2
```

**Mocking modules:**
```python
@pytest.mark.asyncio
async def test_chat_returns_text():
    mock_response = MagicMock()
    mock_response.text = "i'm a sarcastic bot"
    
    with patch("services.gemini.genai") as mock_genai:
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
        mock_genai.Client.return_value = mock_client
        
        service = GeminiService(api_key="fake-key")
        result = await service.chat(system_prompt="You are sarcastic.", conversation=[])
        assert result == "i'm a sarcastic bot"
```

**Async mocking:**
- `AsyncMock()` for coroutines
- `@pytest.mark.asyncio` decorator required for async test functions
- `await` calls on AsyncMock instances work correctly

**What to Mock:**
- External API calls (Gemini, YouTube, yt-dlp)
- File I/O operations (cache checking, downloads)
- Discord client interactions (voice, channels)
- Database connections (via in-memory SQLite instead)

**What NOT to Mock:**
- Pure business logic (queue advance, shuffle logic)
- Data model creation and access (Track, MusicQueue, MessageBuffer)
- Utility functions (format_duration, progress_bar)
- Helper functions (make_track factory)

## Fixtures and Factories

**Test Data:**
- `make_track()` factory in `test_queue.py` — creates Track with defaults
- `MOCK_SEARCH_RESULT`, `MOCK_EXTRACT_RESULT`, `MOCK_LIVESTREAM_RESULT` constants in `test_youtube.py` — predefined API responses
- `MOCK_PLAYLIST_RESULT` in `test_youtube.py` — 60 fake playlist entries for pagination testing

**Example from `test_youtube.py`:**
```python
MOCK_SEARCH_RESULT = {
    "entries": [
        {
            "id": "abc123",
            "title": "Test Song - Test Artist",
            "url": "https://www.youtube.com/watch?v=abc123",
            "duration": 200,
            "thumbnails": [{"url": "https://i.ytimg.com/vi/abc123/default.jpg"}],
        },
        # ... more entries
    ]
}
```

**Location:**
- Test fixtures at module level (not in conftest.py)
- Mock data as module-level constants
- Factories as helper functions defined at top of test file

## Database Testing

**Async Fixtures:**
- In-memory SQLite via `aiosqlite.connect(":memory:")`
- Fixtures use `@pytest_asyncio.fixture` decorator
- Schema initialized with `await init_db(conn)` for each test
- Connection closed in fixture cleanup: `yield conn; await conn.close()`

**Example from `tests/test_database.py`:**
```python
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
```

## Async Testing

**Marking:**
- `@pytest.mark.asyncio` on every async test function
- `@pytest_asyncio.fixture` for async fixtures (not `@pytest.fixture`)

**Pattern:**
```python
@pytest.mark.asyncio
async def test_chat_api_error_raises(self):
    with patch("services.gemini.genai") as mock_genai:
        mock_client = MagicMock()
        mock_error = Exception("API Error")
        mock_client.aio.models.generate_content = AsyncMock(side_effect=mock_error)
        mock_genai.Client.return_value = mock_client
        
        service = GeminiService(api_key="fake-key")
        with pytest.raises(GeminiAPIError):
            await service.chat(system_prompt="test", conversation=[])
```

## Error Testing

**Exception Testing:**
- `pytest.raises()` context manager to assert exceptions
- Match parameter for regex matching: `pytest.raises(ValueError, match="[Ll]ivestream")`
- Side effects in mocks: `AsyncMock(side_effect=Exception("API Error"))`

**Example from `test_youtube.py`:**
```python
def test_extract_livestream_raises(self, yt_service):
    with patch.object(yt_service, "_extract", return_value=MOCK_LIVESTREAM_RESULT):
        with pytest.raises(ValueError, match="[Ll]ivestream"):
            yt_service.extract("https://youtube.com/watch?v=live123")
```

## Coverage

**Requirements:** Not detected; no coverage targets enforced

**View Coverage:**
```bash
pytest --cov=. --cov-report=html      # If coverage plugin installed
```

Note: `pytest-cov` not in `requirements.txt`; coverage not automated.

## Test Types

**Unit Tests:**
- Scope: Single function or class method
- Approach: Test expected behavior with mocked dependencies
- Examples: `test_skip_advances_index()`, `test_format_duration()`, `test_search_returns_results()`
- Coverage: Queue logic, database queries, YouTube metadata extraction, formatting

**Integration Tests:**
- Scope: Multi-component interaction (less common in this codebase)
- Approach: Real in-memory database with schema, mocked API services
- Examples: Database tests verify schema + query helpers together
- Coverage: Limited; mostly component-level testing

**E2E Tests:**
- Framework: Not used
- Discord interactions with real voice/commands require manual testing

## What Is Tested

**High Coverage:**
- `models/` — Queue logic, message buffer, user profiles (15+ tests covering edge cases)
- `database.py` — Schema creation, query helpers (log_song, update_artist_count, etc.)
- `services/youtube.py` — Search, extract, playlist handling with mocked yt-dlp
- `services/audio.py` — Cache lookup, cleanup logic
- `utils/formatters.py` — Duration formatting, progress bar rendering
- `personality/prompts.py` — Prompt builders with mood/seasonal context

**Partial Coverage:**
- `services/gemini.py` — Chat and error scenarios (mocked API)
- `services/` audio fallback logic (stream fallback tested via exceptions)

**Not Tested (Discord-specific):**
- `cogs/` — Command handlers (require Discord bot/interaction mocking)
- `bot.py` — Event handlers, background tasks, service wiring
- `events.py` — Voice event roasts and reactions
- Direct Discord API calls (interactions, voice connections)

## Naming Test Functions

**Convention:** `test_<scenario>_<expected_result>`

**Examples:**
- `test_add_track` — Adding a track increases queue length
- `test_skip_ignores_single_loop` — Skip bypasses SINGLE loop mode
- `test_advance_repeats_on_single_loop` — Advance respects SINGLE loop (doesn't skip)
- `test_extract_livestream_raises` — Livestream URL raises ValueError
- `test_half_progress` — Progress bar at 50% shows correct format

## Test Isolation

**State Isolation:**
- No shared state between tests (each creates fresh objects)
- Database tests use new in-memory connection per test
- Fixtures with `yield` cleanup after each test

**Mocking Isolation:**
- `patch()` context managers reset mocks after each test
- No global mock state pollution
- Each test is independent

## Assertions

**Style:**
- Simple `assert` statements (not `self.assertEqual()`)
- Multiple assertions per test allowed if related
- Assertion messages optional but recommended for clarity

**Examples from codebase:**
```python
assert len(q.tracks) == 1
assert q.tracks[0] is track
assert q.current_index == 0
assert result is None
assert results[0]["video_id"] == "abc123"
assert len(results) == 50  # MAX_PLAYLIST_IMPORT
```

## Test Organization by Layer

**Models (`tests/test_*.py` for models/):**
- `test_queue.py` — 156 lines, 7 test classes, 20+ test methods
- `test_message_buffer.py` — 68 lines, 3 test classes
- `test_user_profile.py` — Tests user taste summary generation

**Services (`tests/test_*.py` for services/):**
- `test_youtube.py` — 125 lines, search/extract/playlist/is_url tests
- `test_audio.py` — 61 lines, cache lookup and cleanup tests
- `test_gemini.py` — 58 lines, async chat and error handling tests

**Database (`test_database.py`):**
- `test_database.py` — 125 lines, schema + query helpers
- `test_database_phase2.py` — 194 lines, Phase 2 features (image logging, mood)

**Utilities (`tests/test_*.py` for utils/):**
- `test_formatters.py` — 42 lines, duration and progress bar formatting

**Personality (`tests/test_*.py` for personality/):**
- `test_prompts.py` — Prompt builder functions
- `test_responses.py` — Personality response templates
- `test_seasonal.py` — Seasonal context injection

## Running Specific Tests

```bash
# Run all tests in a file
pytest tests/test_queue.py

# Run a single test class
pytest tests/test_queue.py::TestMusicQueueSkip

# Run a single test method
pytest tests/test_queue.py::TestMusicQueueSkip::test_skip_ignores_single_loop

# Run tests matching a pattern
pytest -k "test_add" tests/

# Run async tests only
pytest -k "async" tests/

# Verbose output
pytest -v tests/test_queue.py
```

---

*Testing analysis: 2026-06-01*
