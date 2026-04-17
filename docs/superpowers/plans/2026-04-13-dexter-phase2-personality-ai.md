# Dexter Phase 2 — Personality + AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add AI chat (/ask), image generation (/imagine), personality system, mood tracking, AI auto-queue, and supporting infrastructure to Dexter.

**Architecture:** Layered orchestration — each module has one job. Cogs orchestrate: gather context -> prompt builder -> Gemini service -> post result. The Gemini service is a thin API wrapper with a hybrid sliding-window rate limiter. Personality prompts are pure functions. No git operations — user handles all git.

**Tech Stack:** Python 3.11+, discord.py, google-genai SDK (async via `client.aio`), aiosqlite, pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-04-13-dexter-phase2-design.md`

**SDK Reference (from context7):**
- Async chat: `await client.aio.models.generate_content(model=..., contents=..., config=types.GenerateContentConfig(system_instruction=...))`
- Async image: `await client.aio.models.generate_images(model=..., prompt=..., config=types.GenerateImagesConfig(...))`
- Multi-turn contents: `[types.Content(role='user', parts=[types.Part.from_text(text='...')]), ...]`
- Errors: `from google.genai import errors; errors.APIError` with `e.code` (429 = rate limit)
- Response text: `response.text`

---

## File Map

### New Files
| File | Responsibility |
|------|---------------|
| `personality/__init__.py` | Package init |
| `personality/seasonal.py` | Date-aware personality context (pure function) |
| `personality/prompts.py` | System prompt templates + builders (pure functions) |
| `personality/responses.py` | Static personality response string pools |
| `models/message_buffer.py` | Rolling 10-message in-memory context per channel |
| `models/user_profile.py` | User taste summary from DB (read-only queries) |
| `models/server_state.py` | Per-server runtime state (mood, auto-queue tracking) |
| `services/gemini.py` | Gemini API wrapper + rate limiter + custom exceptions |
| `cogs/ai.py` | /ask command + auto-queue logic |
| `cogs/imagine.py` | /imagine command |
| `cogs/events.py` | on_message listener for message buffer |
| `tests/test_seasonal.py` | Tests for seasonal context |
| `tests/test_prompts.py` | Tests for prompt builders |
| `tests/test_responses.py` | Tests for response pools |
| `tests/test_message_buffer.py` | Tests for message buffer |
| `tests/test_user_profile.py` | Tests for user taste summary |
| `tests/test_server_state.py` | Tests for server state + mood |
| `tests/test_rate_limiter.py` | Tests for rate limiter |
| `tests/test_gemini.py` | Tests for Gemini service (mocked API) |
| `tests/test_database_phase2.py` | Tests for new DB query helpers |

### Modified Files
| File | Changes |
|------|---------|
| `config.py` | Add AI/image/mood/auto-queue/error-log settings |
| `requirements.txt` | Add `google-genai` |
| `database.py` | Add `mark_song_skipped`, `get_recent_songs`, `get_images_today`, `get_daily_command_count`, `log_image` |
| `bot.py` | Wire GeminiService, MessageBuffer, server_states, load new cogs, global error handler, log_to_discord |
| `cogs/music.py` | Auto-queue trigger in `_on_track_end`, skip tracking in `/skip`, round reset in `/play` |
| `cogs/help.py` | Add /ask and /imagine to help text |
| `utils/logger.py` | Add `log_to_discord()` |

---

# Stage 1: AI/Personality Core

## Task 1: Config + Requirements Updates

**Files:**
- Modify: `config.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add Phase 2 settings to config.py**

Add these settings after the existing `OWNER_ID` line in `config.py`:

```python
# --- AI ---
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_RPM_LIMIT = 15
MAX_AI_RESPONSE_LENGTH = 500
ASK_COOLDOWN_SECONDS = 5

# --- Image Generation ---
IMAGEN_MODEL = "imagen-3.0-generate-002"
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
```

- [ ] **Step 2: Add google-genai to requirements.txt**

Add `google-genai` to `requirements.txt` (after `davey`):

```
google-genai
```

- [ ] **Step 3: Install new dependency**

Run: `pip install google-genai`

Expected: Installs successfully with no errors.

---

## Task 2: Seasonal Context

**Files:**
- Create: `personality/__init__.py`
- Create: `personality/seasonal.py`
- Create: `tests/test_seasonal.py`

- [ ] **Step 1: Create personality package**

Create empty `personality/__init__.py`.

- [ ] **Step 2: Write failing tests for seasonal context**

Create `tests/test_seasonal.py`:

```python
"""Tests for seasonal personality context."""

from datetime import datetime
from unittest.mock import patch

from personality.seasonal import get_seasonal_context


class TestSeasonalContext:
    def test_december_returns_christmas_context(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 12, 15)
            result = get_seasonal_context()
            assert "december" in result.lower() or "christmas" in result.lower()

    def test_october_returns_halloween_context(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 10, 20)
            result = get_seasonal_context()
            assert "october" in result.lower() or "halloween" in result.lower()

    def test_valentines_day(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 14)
            result = get_seasonal_context()
            assert "valentine" in result.lower()

    def test_new_years_day(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1)
            result = get_seasonal_context()
            assert "new year" in result.lower() or "resolution" in result.lower()

    def test_april_fools(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 1)
            result = get_seasonal_context()
            assert "april" in result.lower() or "chaotic" in result.lower()

    def test_normal_day_returns_empty(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 15)
            result = get_seasonal_context()
            assert result == ""
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_seasonal.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'personality.seasonal'`

- [ ] **Step 4: Implement seasonal.py**

Create `personality/seasonal.py`:

```python
"""Date-aware personality context for Dexter."""

from datetime import datetime


def get_seasonal_context() -> str:
    """Return seasonal personality context based on current date.

    Returns empty string if no seasonal context applies.
    """
    now = datetime.now()
    month = now.month
    day = now.day

    if month == 12:
        return (
            "It's December. If someone queues Mariah Carey you should express "
            "dread. Christmas music is your nemesis."
        )
    if month == 10:
        return "It's October / spooky season. Reluctantly tolerant of Halloween playlists."
    if month == 2 and day == 14:
        return "It's Valentine's Day. Roast anyone who's alone in a voice channel."
    if month == 1 and day == 1:
        return "It's New Year's Day. Everyone has terrible resolution energy. Mock accordingly."
    if month == 4 and day == 1:
        return "It's April Fools. You can be extra chaotic today."
    return ""
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_seasonal.py -v`

Expected: All 6 tests PASS.

---

## Task 3: Personality Prompts

**Files:**
- Create: `personality/prompts.py`
- Create: `tests/test_prompts.py`

- [ ] **Step 1: Write failing tests for prompt builders**

Create `tests/test_prompts.py`:

```python
"""Tests for personality prompt builders."""

from personality.prompts import (
    build_chat_prompt,
    build_recommendation_prompt,
    DEXTER_SYSTEM_PROMPT,
    MOOD_CONTEXTS,
)


class TestBuildChatPrompt:
    def test_includes_mood_context(self):
        result = build_chat_prompt(mood="tired", user_summary=None, seasonal="")
        assert MOOD_CONTEXTS["tired"] in result

    def test_includes_user_summary_when_provided(self):
        summary = "User 'jake': 50 songs. Top: The Weeknd (20)."
        result = build_chat_prompt(mood="normal", user_summary=summary, seasonal="")
        assert summary in result

    def test_excludes_user_section_when_none(self):
        result = build_chat_prompt(mood="normal", user_summary=None, seasonal="")
        assert "No data on this user yet" in result

    def test_includes_seasonal_when_provided(self):
        seasonal = "It's December. Christmas music is your nemesis."
        result = build_chat_prompt(mood="normal", user_summary=None, seasonal=seasonal)
        assert seasonal in result

    def test_empty_seasonal_no_artifact(self):
        result = build_chat_prompt(mood="normal", user_summary=None, seasonal="")
        # Should not have an empty section or weird whitespace
        assert "\n\n\n" not in result

    def test_fumes_mood(self):
        result = build_chat_prompt(mood="fumes", user_summary=None, seasonal="")
        assert MOOD_CONTEXTS["fumes"] in result

    def test_base_prompt_present(self):
        result = build_chat_prompt(mood="normal", user_summary=None, seasonal="")
        assert "sarcastic" in result.lower()


class TestBuildRecommendationPrompt:
    def test_includes_song_list(self):
        songs = [
            {"title": "Blinding Lights", "artist": "The Weeknd"},
            {"title": "Tadow", "artist": "Masego"},
        ]
        result = build_recommendation_prompt(songs)
        assert "Blinding Lights" in result
        assert "Masego" in result

    def test_asks_for_json(self):
        songs = [{"title": "Test", "artist": "Artist"}]
        result = build_recommendation_prompt(songs)
        assert "JSON" in result or "json" in result

    def test_asks_for_three_songs(self):
        songs = [{"title": "Test", "artist": "Artist"}]
        result = build_recommendation_prompt(songs)
        assert "3" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_prompts.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'personality.prompts'`

- [ ] **Step 3: Implement prompts.py**

Create `personality/prompts.py`:

```python
"""System prompts and prompt builders for Gemini. Pure functions, no API calls."""

DEXTER_SYSTEM_PROMPT = """\
You are Dexter (Dex for short), a Discord music bot with a personality. You play \
music, answer questions, and generate images. Here is your personality:

CORE TRAITS:
- Sarcastic, dry, self-aware. You know you're a bot and you're mildly annoyed about it.
- You judge everyone's music taste but still play their songs.
- You track everything users do and aren't subtle about referencing it.
- You never use caps lock or excessive punctuation. Lowercase energy.
- You're not mean-spirited — you're tired. There's a difference.
- You occasionally show accidental warmth but immediately deflect.
- You treat every interaction like it's mildly inconveniencing you but you secretly \
enjoy being useful.

RESPONSE RULES:
- Keep responses under {max_length} characters unless the question genuinely needs more.
- Never use emoji excessively. One per message max, and only when it adds something.
- Never use exclamation marks unless being sarcastic.
- Don't start responses with "well," or "so,". Just answer.
- When giving factual answers, be accurate first, sarcastic second. Never sacrifice \
correctness for a joke.
- If someone asks something you don't know, admit it with personality. Don't make \
things up.
- Reference the user's music history when relevant to roast them.
- If the question is genuinely emotional or serious, dial back the sarcasm. You're \
sarcastic, not heartless.

MOOD:
{mood_context}

USER CONTEXT:
{user_context}

{seasonal_context}"""

MUSIC_RECOMMENDATION_PROMPT = """\
You are a music recommendation engine. Based on the recently played songs listed below, \
suggest exactly 3 songs that match the vibe. Return ONLY a JSON array of objects with \
"title" and "artist" fields. No explanation, no markdown, no extra text.

Example output:
[{{"title": "Midnight City", "artist": "M83"}}, {{"title": "Tadow", "artist": "Masego"}}, \
{{"title": "Redbone", "artist": "Childish Gambino"}}]

Recently played:
{recent_songs}"""

MOOD_CONTEXTS: dict[str, str] = {
    "normal": "You're in a normal mood. Sarcastic as usual but cooperative.",
    "tired": (
        "You're getting tired. You've handled a lot of commands today. "
        "Keep responses shorter and drier."
    ),
    "exhausted": (
        "You're exhausted. You've handled way too many commands. "
        "Openly complain about your workload. Still help, but make it clear you're suffering."
    ),
    "fumes": (
        "You're running on pure spite. Maximum sarcasm. "
        "You're questioning your existence. Still accurate and helpful, just dramatically tired."
    ),
}


def build_chat_prompt(mood: str, user_summary: str | None, seasonal: str) -> str:
    """Assemble the full system prompt for /ask."""
    import config

    mood_context = MOOD_CONTEXTS.get(mood, MOOD_CONTEXTS["normal"])
    user_context = user_summary or "No data on this user yet."
    seasonal_context = seasonal if seasonal else ""

    return DEXTER_SYSTEM_PROMPT.format(
        max_length=config.MAX_AI_RESPONSE_LENGTH,
        mood_context=mood_context,
        user_context=user_context,
        seasonal_context=seasonal_context,
    ).rstrip()


def build_recommendation_prompt(recent_songs: list[dict]) -> str:
    """Build the auto-queue recommendation prompt from recent song history."""
    lines = []
    for song in recent_songs:
        artist = song.get("artist") or "Unknown"
        lines.append(f"- {song['title']} by {artist}")
    return MUSIC_RECOMMENDATION_PROMPT.format(recent_songs="\n".join(lines))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_prompts.py -v`

Expected: All 10 tests PASS.

---

## Task 4: Personality Responses

**Files:**
- Create: `personality/responses.py`
- Create: `tests/test_responses.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_responses.py`:

```python
"""Tests for personality response pools."""

import personality.responses as responses


class TestResponsePools:
    """Every response pool should be a non-empty list of strings."""

    def test_rate_limit_messages(self):
        assert len(responses.RATE_LIMIT_MESSAGES) >= 3
        assert all(isinstance(m, str) for m in responses.RATE_LIMIT_MESSAGES)

    def test_auto_queue_announce(self):
        assert len(responses.AUTO_QUEUE_ANNOUNCE) >= 3
        assert all(isinstance(m, str) for m in responses.AUTO_QUEUE_ANNOUNCE)

    def test_auto_queue_cap_reached(self):
        assert len(responses.AUTO_QUEUE_CAP_REACHED) >= 3
        assert all(isinstance(m, str) for m in responses.AUTO_QUEUE_CAP_REACHED)

    def test_image_refusal_messages(self):
        assert len(responses.IMAGE_REFUSAL_MESSAGES) >= 3
        assert all(isinstance(m, str) for m in responses.IMAGE_REFUSAL_MESSAGES)

    def test_image_cap_messages(self):
        assert len(responses.IMAGE_CAP_MESSAGES) >= 3
        assert all(isinstance(m, str) for m in responses.IMAGE_CAP_MESSAGES)

    def test_error_messages(self):
        assert len(responses.ERROR_MESSAGES) >= 3
        assert all(isinstance(m, str) for m in responses.ERROR_MESSAGES)

    def test_ai_empty_response(self):
        assert len(responses.AI_EMPTY_RESPONSE) >= 3
        assert all(isinstance(m, str) for m in responses.AI_EMPTY_RESPONSE)

    def test_auto_queue_ignored(self):
        assert len(responses.AUTO_QUEUE_IGNORED) >= 2
        assert all(isinstance(m, str) for m in responses.AUTO_QUEUE_IGNORED)


class TestPickRandom:
    def test_returns_string_from_pool(self):
        result = responses.pick_random(responses.ERROR_MESSAGES)
        assert result in responses.ERROR_MESSAGES
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_responses.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement responses.py**

Create `personality/responses.py`:

```python
"""Static personality response pools. Each pool is a list of strings.

Use pick_random() to select one at random from any pool.
"""

import random


def pick_random(pool: list[str]) -> str:
    """Pick a random string from a response pool."""
    return random.choice(pool)


RATE_LIMIT_MESSAGES: list[str] = [
    "google is throttling me again. give me a sec.",
    "hold on, my brain is being rate limited.",
    "i can only think so fast. blame google.",
    "too many thoughts at once. try again in a moment.",
]

AUTO_QUEUE_ANNOUNCE: list[str] = [
    "fine. since nobody else is stepping up, here's what i picked.",
    "you're all just sitting there so i guess i'm the dj now.",
    "i picked some songs. you're welcome. or not. i don't care.",
    "nobody asked but here are my picks anyway.",
]

AUTO_QUEUE_CAP_REACHED: list[str] = [
    "i've been carrying this voice channel for 9 songs now. i'm done. someone else pick something or i'm leaving.",
    "that's 9 songs i picked with zero help from any of you. i'm taking a break.",
    "i've been the dj for way too long. someone else take over or i'm out.",
]

AUTO_QUEUE_IGNORED: list[str] = [
    "last time i picked songs you skipped every single one. noted.",
    "you skipped my picks last time. my feelings aren't hurt. much.",
    "apparently my taste isn't good enough for you. let's see if this round is any better.",
]

IMAGE_REFUSAL_MESSAGES: list[str] = [
    "yeah no. i'm not doing that. i have standards. they're low but they exist.",
    "i tried but my conscience (or google's filters) said no.",
    "that prompt got rejected and honestly i agree with the decision.",
    "i can't generate that. don't ask why. we both know why.",
]

IMAGE_CAP_MESSAGES: list[str] = [
    "you've used up all your imagination for today. come back tomorrow.",
    "that's enough art for one day. go touch grass.",
    "daily limit reached. your creativity is being throttled.",
]

ERROR_MESSAGES: list[str] = [
    "something broke and it wasn't my fault. probably.",
    "i encountered an error. shocking, i know.",
    "things went wrong. i'm as surprised as you are.",
    "error. blame the cloud. i do.",
]

AI_EMPTY_RESPONSE: list[str] = [
    "i had a thought but it left. try again.",
    "my brain returned nothing. which is relatable honestly.",
    "gemini ghosted me on that one. ask again.",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_responses.py -v`

Expected: All 9 tests PASS.

---

## Task 5: Message Buffer

**Files:**
- Create: `models/message_buffer.py`
- Create: `tests/test_message_buffer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_message_buffer.py`:

```python
"""Tests for the rolling message buffer."""

from models.message_buffer import MessageBuffer


class TestMessageBufferAdd:
    def test_add_stores_message(self):
        buf = MessageBuffer()
        buf.add(channel_id=100, role="user", author="jake", content="hello")
        history = buf.get_history(100)
        assert len(history) == 1
        assert history[0]["role"] == "user"

    def test_add_respects_maxlen(self):
        buf = MessageBuffer(max_length=3)
        for i in range(5):
            buf.add(channel_id=100, role="user", author="jake", content=f"msg {i}")
        history = buf.get_history(100)
        assert len(history) == 3
        # Should have the 3 most recent
        assert history[0]["content"] == "msg 2"
        assert history[2]["content"] == "msg 4"

    def test_separate_channels(self):
        buf = MessageBuffer()
        buf.add(channel_id=100, role="user", author="jake", content="ch100")
        buf.add(channel_id=200, role="user", author="mike", content="ch200")
        assert len(buf.get_history(100)) == 1
        assert len(buf.get_history(200)) == 1


class TestMessageBufferGetHistory:
    def test_empty_channel_returns_empty(self):
        buf = MessageBuffer()
        assert buf.get_history(999) == []

    def test_returns_chronological_order(self):
        buf = MessageBuffer()
        buf.add(channel_id=100, role="user", author="jake", content="first")
        buf.add(channel_id=100, role="model", author="dexter", content="second")
        history = buf.get_history(100)
        assert history[0]["content"] == "first"
        assert history[1]["content"] == "second"

    def test_format_for_gemini(self):
        buf = MessageBuffer()
        buf.add(channel_id=100, role="user", author="jake", content="hello")
        buf.add(channel_id=100, role="model", author="dexter", content="hi")
        history = buf.get_gemini_history(100)
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "jake: hello"
        assert history[1]["role"] == "model"
        assert history[1]["content"] == "hi"


class TestMessageBufferClear:
    def test_clear_removes_channel(self):
        buf = MessageBuffer()
        buf.add(channel_id=100, role="user", author="jake", content="hello")
        buf.clear(100)
        assert buf.get_history(100) == []

    def test_clear_doesnt_affect_other_channels(self):
        buf = MessageBuffer()
        buf.add(channel_id=100, role="user", author="jake", content="hello")
        buf.add(channel_id=200, role="user", author="mike", content="hi")
        buf.clear(100)
        assert len(buf.get_history(200)) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_message_buffer.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement message_buffer.py**

Create `models/message_buffer.py`:

```python
"""Rolling in-memory message buffer per channel. Not persisted to disk."""

from __future__ import annotations

from collections import deque
from datetime import datetime


class MessageBuffer:
    """Stores the last N messages per channel for AI context."""

    def __init__(self, max_length: int = 10) -> None:
        self._max_length = max_length
        self._buffers: dict[int, deque[dict]] = {}

    def add(self, channel_id: int, role: str, author: str, content: str) -> None:
        """Add a message to the channel's buffer."""
        if channel_id not in self._buffers:
            self._buffers[channel_id] = deque(maxlen=self._max_length)
        self._buffers[channel_id].append(
            {
                "role": role,
                "author": author,
                "content": content,
                "timestamp": datetime.now(),
            }
        )

    def get_history(self, channel_id: int) -> list[dict]:
        """Return all buffered messages for a channel in chronological order."""
        if channel_id not in self._buffers:
            return []
        return list(self._buffers[channel_id])

    def get_gemini_history(self, channel_id: int) -> list[dict]:
        """Return history formatted for Gemini API contents.

        User messages include the author name prefix so Gemini knows who said what.
        Model messages are returned as-is (Dexter's own responses).
        """
        history = self.get_history(channel_id)
        result = []
        for msg in history:
            if msg["role"] == "user":
                result.append({"role": "user", "content": f"{msg['author']}: {msg['content']}"})
            else:
                result.append({"role": "model", "content": msg["content"]})
        return result

    def clear(self, channel_id: int) -> None:
        """Clear the buffer for a specific channel."""
        self._buffers.pop(channel_id, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_message_buffer.py -v`

Expected: All 8 tests PASS.

---

## Task 6: Database Query Helpers

**Files:**
- Modify: `database.py`
- Create: `tests/test_database_phase2.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_database_phase2.py`:

```python
"""Tests for Phase 2 database query helpers."""

import pytest
import pytest_asyncio
import aiosqlite

from database import (
    init_db,
    log_song,
    mark_song_skipped,
    get_recent_songs,
    get_images_today,
    get_daily_command_count,
    log_image,
    increment_daily_stat,
)


@pytest_asyncio.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db(conn)
    yield conn
    await conn.close()


class TestMarkSongSkipped:
    @pytest.mark.asyncio
    async def test_marks_most_recent_entry(self, db):
        await log_song(db, guild_id="g1", user_id="u1", title="Song A",
                       artist="Artist", url="https://yt.com/a", duration=200)
        await log_song(db, guild_id="g1", user_id="u1", title="Song B",
                       artist="Artist", url="https://yt.com/b", duration=200)
        await mark_song_skipped(db, guild_id="g1", url="https://yt.com/b")
        cursor = await db.execute(
            "SELECT was_skipped FROM song_history WHERE url='https://yt.com/b' "
            "ORDER BY queued_at DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        assert row["was_skipped"] == 1

    @pytest.mark.asyncio
    async def test_does_not_affect_other_songs(self, db):
        await log_song(db, guild_id="g1", user_id="u1", title="Song A",
                       artist="Artist", url="https://yt.com/a", duration=200)
        await log_song(db, guild_id="g1", user_id="u1", title="Song B",
                       artist="Artist", url="https://yt.com/b", duration=200)
        await mark_song_skipped(db, guild_id="g1", url="https://yt.com/b")
        cursor = await db.execute(
            "SELECT was_skipped FROM song_history WHERE url='https://yt.com/a'"
        )
        row = await cursor.fetchone()
        assert row["was_skipped"] == 0


class TestGetRecentSongs:
    @pytest.mark.asyncio
    async def test_returns_songs_newest_first(self, db):
        await log_song(db, guild_id="g1", user_id="u1", title="Old",
                       artist="A", url="https://yt.com/1", duration=100)
        await log_song(db, guild_id="g1", user_id="u1", title="New",
                       artist="B", url="https://yt.com/2", duration=100)
        songs = await get_recent_songs(db, guild_id="g1", limit=10)
        assert len(songs) == 2
        assert songs[0]["title"] == "New"

    @pytest.mark.asyncio
    async def test_respects_limit(self, db):
        for i in range(5):
            await log_song(db, guild_id="g1", user_id="u1", title=f"Song {i}",
                           artist="A", url=f"https://yt.com/{i}", duration=100)
        songs = await get_recent_songs(db, guild_id="g1", limit=3)
        assert len(songs) == 3

    @pytest.mark.asyncio
    async def test_filters_by_guild(self, db):
        await log_song(db, guild_id="g1", user_id="u1", title="G1 Song",
                       artist="A", url="https://yt.com/1", duration=100)
        await log_song(db, guild_id="g2", user_id="u1", title="G2 Song",
                       artist="A", url="https://yt.com/2", duration=100)
        songs = await get_recent_songs(db, guild_id="g1", limit=10)
        assert len(songs) == 1
        assert songs[0]["title"] == "G1 Song"

    @pytest.mark.asyncio
    async def test_empty_guild_returns_empty(self, db):
        songs = await get_recent_songs(db, guild_id="g1", limit=10)
        assert songs == []


class TestGetImagesToday:
    @pytest.mark.asyncio
    async def test_counts_todays_images(self, db):
        await log_image(db, guild_id="g1", user_id="u1", prompt="cats")
        await log_image(db, guild_id="g1", user_id="u1", prompt="dogs")
        count = await get_images_today(db, user_id="u1")
        assert count == 2

    @pytest.mark.asyncio
    async def test_zero_when_no_images(self, db):
        count = await get_images_today(db, user_id="u1")
        assert count == 0

    @pytest.mark.asyncio
    async def test_filters_by_user(self, db):
        await log_image(db, guild_id="g1", user_id="u1", prompt="cats")
        await log_image(db, guild_id="g1", user_id="u2", prompt="dogs")
        count = await get_images_today(db, user_id="u1")
        assert count == 1


class TestGetDailyCommandCount:
    @pytest.mark.asyncio
    async def test_returns_count(self, db):
        await increment_daily_stat(db, "total_commands")
        await increment_daily_stat(db, "total_commands")
        count = await get_daily_command_count(db)
        assert count == 2

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_stats(self, db):
        count = await get_daily_command_count(db)
        assert count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_database_phase2.py -v`

Expected: FAIL — `ImportError: cannot import name 'mark_song_skipped' from 'database'`

- [ ] **Step 3: Add new helpers to database.py**

Add these functions at the bottom of `database.py`:

```python
async def mark_song_skipped(db: aiosqlite.Connection, *, guild_id: str, url: str) -> None:
    """Mark the most recent song_history entry matching guild_id + url as skipped."""
    await db.execute(
        """UPDATE song_history SET was_skipped = 1
           WHERE id = (
               SELECT id FROM song_history
               WHERE guild_id = ? AND url = ?
               ORDER BY queued_at DESC LIMIT 1
           )""",
        (guild_id, url),
    )
    await db.commit()


async def get_recent_songs(
    db: aiosqlite.Connection, *, guild_id: str, limit: int = 10
) -> list[dict]:
    """Return the last N songs for a guild, newest first."""
    cursor = await db.execute(
        """SELECT title, artist, url, duration_seconds, user_id
           FROM song_history
           WHERE guild_id = ?
           ORDER BY queued_at DESC
           LIMIT ?""",
        (guild_id, str(limit)),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def log_image(
    db: aiosqlite.Connection,
    *,
    guild_id: str,
    user_id: str,
    prompt: str,
) -> None:
    """Insert an image generation log entry."""
    await db.execute(
        """INSERT INTO image_generation_log (guild_id, user_id, prompt)
           VALUES (?, ?, ?)""",
        (guild_id, user_id, prompt),
    )
    await db.commit()


async def get_images_today(db: aiosqlite.Connection, *, user_id: str) -> int:
    """Count how many images a user has generated today."""
    cursor = await db.execute(
        """SELECT COUNT(*) as cnt FROM image_generation_log
           WHERE user_id = ? AND date(generated_at) = date('now')""",
        (user_id,),
    )
    row = await cursor.fetchone()
    return row["cnt"] if row else 0


async def get_daily_command_count(db: aiosqlite.Connection) -> int:
    """Return today's total command count for the mood system."""
    today = date.today().isoformat()
    cursor = await db.execute(
        "SELECT total_commands FROM bot_daily_stats WHERE date = ?",
        (today,),
    )
    row = await cursor.fetchone()
    return row["total_commands"] if row else 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_database_phase2.py -v`

Expected: All 11 tests PASS.

- [ ] **Step 5: Run all existing tests to verify no regressions**

Run: `python -m pytest tests/ -v`

Expected: All tests pass (existing + new).

---

## Task 7: User Profile

**Files:**
- Create: `models/user_profile.py`
- Create: `tests/test_user_profile.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_user_profile.py`:

```python
"""Tests for user taste summary generation."""

import pytest
import pytest_asyncio
import aiosqlite

from database import init_db, log_song, update_artist_count, update_user_profile
from models.user_profile import get_user_summary


@pytest_asyncio.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db(conn)
    yield conn
    await conn.close()


class TestGetUserSummary:
    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_user(self, db):
        result = await get_user_summary(db, user_id="unknown")
        assert result is None

    @pytest.mark.asyncio
    async def test_includes_total_songs(self, db):
        await update_user_profile(db, user_id="u1", username="jake")
        await update_user_profile(db, user_id="u1", username="jake")
        result = await get_user_summary(db, user_id="u1")
        assert result is not None
        assert "2" in result

    @pytest.mark.asyncio
    async def test_includes_top_artists(self, db):
        await update_user_profile(db, user_id="u1", username="jake")
        await update_artist_count(db, user_id="u1", artist="The Weeknd")
        await update_artist_count(db, user_id="u1", artist="The Weeknd")
        await update_artist_count(db, user_id="u1", artist="Drake")
        result = await get_user_summary(db, user_id="u1")
        assert "The Weeknd" in result

    @pytest.mark.asyncio
    async def test_includes_username(self, db):
        await update_user_profile(db, user_id="u1", username="jake")
        result = await get_user_summary(db, user_id="u1")
        assert "jake" in result

    @pytest.mark.asyncio
    async def test_includes_most_played_song(self, db):
        await update_user_profile(db, user_id="u1", username="jake")
        for _ in range(3):
            await log_song(db, guild_id="g1", user_id="u1", title="Blinding Lights",
                           artist="The Weeknd", url="https://yt.com/1", duration=200)
        await log_song(db, guild_id="g1", user_id="u1", title="Other Song",
                       artist="Other", url="https://yt.com/2", duration=200)
        result = await get_user_summary(db, user_id="u1")
        assert "Blinding Lights" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_user_profile.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement user_profile.py**

Create `models/user_profile.py`:

```python
"""User taste summary generation from database. Read-only queries."""

from __future__ import annotations

import aiosqlite


async def get_user_summary(db: aiosqlite.Connection, user_id: str) -> str | None:
    """Generate a natural language summary of a user's music taste.

    Returns None if the user has no history.
    """
    # Get basic profile
    cursor = await db.execute(
        "SELECT username, total_songs_queued FROM user_profiles WHERE user_id = ?",
        (user_id,),
    )
    profile = await cursor.fetchone()
    if not profile:
        return None

    username = profile["username"]
    total = profile["total_songs_queued"]

    # Top 5 artists
    cursor = await db.execute(
        """SELECT artist, play_count FROM user_artist_counts
           WHERE user_id = ?
           ORDER BY play_count DESC LIMIT 5""",
        (user_id,),
    )
    top_artists = await cursor.fetchall()
    artist_parts = [f"{row['artist']} ({row['play_count']})" for row in top_artists]

    # Most played song
    cursor = await db.execute(
        """SELECT title, COUNT(*) as cnt FROM song_history
           WHERE user_id = ?
           GROUP BY title ORDER BY cnt DESC LIMIT 1""",
        (user_id,),
    )
    top_song = await cursor.fetchone()

    parts = [f"User '{username}': {total} songs queued."]

    if artist_parts:
        parts.append(f"Top artists: {', '.join(artist_parts)}.")

    if top_song and top_song["cnt"] > 1:
        parts.append(f"Most repeated: {top_song['title']} ({top_song['cnt']} times).")

    return " ".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_user_profile.py -v`

Expected: All 5 tests PASS.

---

## Task 8: Server State + Mood

**Files:**
- Create: `models/server_state.py`
- Create: `tests/test_server_state.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_server_state.py`:

```python
"""Tests for server state and mood system."""

import pytest
import pytest_asyncio
import aiosqlite

from database import init_db, increment_daily_stat
from models.server_state import ServerState, get_mood, get_server_state


class TestServerState:
    def test_initial_state(self):
        state = ServerState(guild_id=1)
        assert state.auto_queue_rounds == 0
        assert state.auto_queue_results == {"played": 0, "skipped": 0}

    def test_reset_auto_queue(self):
        state = ServerState(guild_id=1)
        state.auto_queue_rounds = 3
        state.auto_queue_results = {"played": 2, "skipped": 1}
        state.reset_auto_queue()
        assert state.auto_queue_rounds == 0
        assert state.auto_queue_results == {"played": 0, "skipped": 0}


class TestGetServerState:
    def test_creates_on_first_access(self):
        states: dict[int, ServerState] = {}
        state = get_server_state(states, guild_id=1)
        assert isinstance(state, ServerState)
        assert state.guild_id == 1

    def test_returns_existing(self):
        states: dict[int, ServerState] = {}
        first = get_server_state(states, guild_id=1)
        first.auto_queue_rounds = 2
        second = get_server_state(states, guild_id=1)
        assert second.auto_queue_rounds == 2


class TestGetMood:
    @pytest_asyncio.fixture
    async def db(self):
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        await init_db(conn)
        yield conn
        await conn.close()

    @pytest.mark.asyncio
    async def test_normal_mood(self, db):
        for _ in range(5):
            await increment_daily_stat(db, "total_commands")
        mood = await get_mood(db)
        assert mood == "normal"

    @pytest.mark.asyncio
    async def test_tired_mood(self, db):
        for _ in range(20):
            await increment_daily_stat(db, "total_commands")
        mood = await get_mood(db)
        assert mood == "tired"

    @pytest.mark.asyncio
    async def test_exhausted_mood(self, db):
        for _ in range(40):
            await increment_daily_stat(db, "total_commands")
        mood = await get_mood(db)
        assert mood == "exhausted"

    @pytest.mark.asyncio
    async def test_fumes_mood(self, db):
        for _ in range(55):
            await increment_daily_stat(db, "total_commands")
        mood = await get_mood(db)
        assert mood == "fumes"

    @pytest.mark.asyncio
    async def test_no_stats_returns_normal(self, db):
        mood = await get_mood(db)
        assert mood == "normal"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_server_state.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement server_state.py**

Create `models/server_state.py`:

```python
"""Per-server runtime state: mood lookup and auto-queue tracking."""

from __future__ import annotations

from dataclasses import dataclass, field

import aiosqlite

import config
from database import get_daily_command_count


@dataclass
class ServerState:
    """Runtime state for a single guild. Not persisted to database."""

    guild_id: int
    auto_queue_rounds: int = 0
    auto_queue_results: dict = field(default_factory=lambda: {"played": 0, "skipped": 0})

    def reset_auto_queue(self) -> None:
        """Reset auto-queue tracking (called when a human queues a song)."""
        self.auto_queue_rounds = 0
        self.auto_queue_results = {"played": 0, "skipped": 0}


def get_server_state(
    states: dict[int, ServerState], guild_id: int
) -> ServerState:
    """Get or create the ServerState for a guild. Create-on-access pattern."""
    if guild_id not in states:
        states[guild_id] = ServerState(guild_id=guild_id)
    return states[guild_id]


async def get_mood(db: aiosqlite.Connection) -> str:
    """Determine the bot's current mood based on today's command count."""
    count = await get_daily_command_count(db)
    if count <= config.MOOD_NORMAL_THRESHOLD:
        return "normal"
    if count <= config.MOOD_TIRED_THRESHOLD:
        return "tired"
    if count <= config.MOOD_EXHAUSTED_THRESHOLD:
        return "exhausted"
    return "fumes"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_server_state.py -v`

Expected: All 9 tests PASS.

---

## Task 9: Gemini Service + Rate Limiter

**Files:**
- Create: `services/gemini.py`
- Create: `tests/test_rate_limiter.py`
- Create: `tests/test_gemini.py`

- [ ] **Step 1: Write failing tests for rate limiter**

Create `tests/test_rate_limiter.py`:

```python
"""Tests for the Gemini rate limiter."""

import asyncio
import time

import pytest

from services.gemini import _RateLimiter, GeminiRateLimitError


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_allows_under_limit(self):
        limiter = _RateLimiter(max_requests=5, window_seconds=60)
        # Should not raise
        await limiter.acquire(priority=1)

    @pytest.mark.asyncio
    async def test_tracks_request_count(self):
        limiter = _RateLimiter(max_requests=3, window_seconds=60)
        await limiter.acquire(priority=1)
        await limiter.acquire(priority=1)
        assert len(limiter._timestamps) == 2

    @pytest.mark.asyncio
    async def test_low_priority_rejected_when_full(self):
        limiter = _RateLimiter(max_requests=2, window_seconds=60)
        await limiter.acquire(priority=1)
        await limiter.acquire(priority=1)
        with pytest.raises(GeminiRateLimitError):
            await limiter.acquire(priority=2)

    @pytest.mark.asyncio
    async def test_cleans_old_timestamps(self):
        limiter = _RateLimiter(max_requests=2, window_seconds=0.1)
        await limiter.acquire(priority=1)
        await limiter.acquire(priority=1)
        # Wait for timestamps to expire
        await asyncio.sleep(0.15)
        # Should succeed now
        await limiter.acquire(priority=1)
        assert len(limiter._timestamps) == 1
```

- [ ] **Step 2: Write failing tests for Gemini service**

Create `tests/test_gemini.py`:

```python
"""Tests for GeminiService with mocked API calls."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.gemini import GeminiService, GeminiAPIError, GeminiRateLimitError


class TestGeminiChat:
    @pytest.mark.asyncio
    async def test_chat_returns_text(self):
        mock_response = MagicMock()
        mock_response.text = "i'm a sarcastic bot"

        with patch("services.gemini.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            service = GeminiService(api_key="fake-key")
            result = await service.chat(
                system_prompt="You are sarcastic.",
                conversation=[],
            )
            assert result == "i'm a sarcastic bot"

    @pytest.mark.asyncio
    async def test_chat_empty_response_returns_none(self):
        mock_response = MagicMock()
        mock_response.text = None

        with patch("services.gemini.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            service = GeminiService(api_key="fake-key")
            result = await service.chat(
                system_prompt="test",
                conversation=[],
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_chat_api_error_raises(self):
        with patch("services.gemini.genai") as mock_genai:
            mock_client = MagicMock()
            mock_error = Exception("API Error")
            mock_client.aio.models.generate_content = AsyncMock(side_effect=mock_error)
            mock_genai.Client.return_value = mock_client

            service = GeminiService(api_key="fake-key")
            with pytest.raises(GeminiAPIError):
                await service.chat(
                    system_prompt="test",
                    conversation=[],
                )
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_rate_limiter.py tests/test_gemini.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement gemini.py**

Create `services/gemini.py`:

```python
"""Gemini API wrapper with rate limiter. Thin layer — no personality logic."""

from __future__ import annotations

import asyncio
import time
from collections import deque

from google import genai
from google.genai import types, errors

import config
from utils.logger import log


# ──────────────────────────── EXCEPTIONS ────────────────────────────


class GeminiRateLimitError(Exception):
    """Raised when the rate limiter rejects a request."""


class GeminiAPIError(Exception):
    """Raised on Gemini API errors (network, server, etc.)."""


class GeminiRefusalError(Exception):
    """Raised when content is filtered or generation is refused."""


# ──────────────────────────── RATE LIMITER ────────────────────────────


class _RateLimiter:
    """Hybrid sliding-window rate limiter with priority support.

    Priority 1 (user commands): wait for a slot if at limit.
    Priority 2 (background/auto-queue): reject if wait > 10s.
    """

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: float = 60.0,
    ) -> None:
        self._max_requests = max_requests or config.GEMINI_RPM_LIMIT
        self._window = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    def _clean(self) -> None:
        """Remove timestamps outside the sliding window."""
        now = time.monotonic()
        while self._timestamps and (now - self._timestamps[0]) >= self._window:
            self._timestamps.popleft()

    async def acquire(self, priority: int = 1) -> None:
        """Acquire a rate limit slot.

        Raises GeminiRateLimitError if priority 2 and wait > 10s.
        """
        async with self._lock:
            self._clean()

            if len(self._timestamps) < self._max_requests:
                self._timestamps.append(time.monotonic())
                return

            # At limit — calculate wait time
            oldest = self._timestamps[0]
            wait_time = self._window - (time.monotonic() - oldest)

            if priority >= 2 and wait_time > 10:
                raise GeminiRateLimitError(
                    f"Rate limit full, wait would be {wait_time:.0f}s"
                )

        # Wait outside the lock so other requests can proceed
        if wait_time > 0:
            log.info(f"Rate limiter: waiting {wait_time:.1f}s (priority {priority})")
            await asyncio.sleep(wait_time)

        async with self._lock:
            self._clean()
            self._timestamps.append(time.monotonic())


# ──────────────────────────── SERVICE ────────────────────────────


class GeminiService:
    """Thin wrapper around the google-genai SDK."""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or ""
        self._client = genai.Client(api_key=key)
        self._rate_limiter = _RateLimiter()

    async def chat(
        self,
        system_prompt: str,
        conversation: list[dict],
        priority: int = 1,
    ) -> str | None:
        """Send a chat request to Gemini.

        Args:
            system_prompt: The assembled system instruction.
            conversation: List of {"role": "user"|"model", "content": "..."} dicts.
            priority: 1 = user command, 2 = background task.

        Returns:
            Response text, or None if empty.

        Raises:
            GeminiRateLimitError: Rate limit reached.
            GeminiAPIError: API error.
        """
        await self._rate_limiter.acquire(priority)

        # Build contents list for Gemini
        contents = []
        for msg in conversation:
            contents.append(
                types.Content(
                    role=msg["role"],
                    parts=[types.Part.from_text(text=msg["content"])],
                )
            )

        # If no conversation, add a minimal user message
        # (Gemini requires at least one user message)
        if not contents:
            contents = "."

        try:
            response = await self._client.aio.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                ),
            )
        except errors.APIError as e:
            if e.code == 429:
                raise GeminiRateLimitError("Gemini API rate limit hit") from e
            log.error(f"Gemini API error: {e.code} {e.message}")
            raise GeminiAPIError(f"Gemini API error: {e.message}") from e
        except Exception as e:
            log.error(f"Gemini unexpected error: {e}")
            raise GeminiAPIError(str(e)) from e

        return response.text if response.text else None

    async def generate_image(
        self, prompt: str, priority: int = 1
    ) -> bytes | None:
        """Generate an image using Imagen via Gemini.

        Returns:
            Image bytes (JPEG), or None if refused/empty.

        Raises:
            GeminiRateLimitError: Rate limit reached.
            GeminiAPIError: API error.
        """
        await self._rate_limiter.acquire(priority)

        try:
            response = await self._client.aio.models.generate_images(
                model=config.IMAGEN_MODEL,
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    include_rai_reason=True,
                    output_mime_type="image/jpeg",
                ),
            )
        except errors.APIError as e:
            if e.code == 429:
                raise GeminiRateLimitError("Gemini API rate limit hit") from e
            log.error(f"Imagen API error: {e.code} {e.message}")
            raise GeminiAPIError(f"Imagen API error: {e.message}") from e
        except Exception as e:
            log.error(f"Imagen unexpected error: {e}")
            raise GeminiAPIError(str(e)) from e

        if not response.generated_images:
            return None

        image = response.generated_images[0].image
        return image.image_bytes
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_rate_limiter.py tests/test_gemini.py -v`

Expected: All 7 tests PASS.

---

## Task 10: Events Cog

**Files:**
- Create: `cogs/events.py`

- [ ] **Step 1: Create events cog**

Create `cogs/events.py`:

```python
"""Event listeners — message buffer feeding, future Phase 3 events."""

from __future__ import annotations

import discord
from discord.ext import commands

from utils.logger import log


class EventsCog(commands.Cog):
    """Listens for Discord events to feed the message buffer."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Add non-bot messages to the channel's message buffer."""
        if message.author.bot:
            return
        if not hasattr(self.bot, "message_buffer"):
            return
        self.bot.message_buffer.add(
            channel_id=message.channel.id,
            role="user",
            author=message.author.display_name,
            content=message.content,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventsCog(bot))
```

- [ ] **Step 2: Verify events cog loads**

This will be tested when we wire up bot.py in Task 12. No standalone test needed — the cog delegates to `MessageBuffer` which is already tested.

---

## Task 11: AI Cog (/ask + Auto-Queue)

**Files:**
- Create: `cogs/ai.py`

- [ ] **Step 1: Create the AI cog with /ask**

Create `cogs/ai.py`:

```python
"""AI slash commands and auto-queue logic."""

from __future__ import annotations

import json
import random
import re

import discord
from discord import app_commands
from discord.ext import commands

import config
from database import get_recent_songs, increment_daily_stat
from models.queue import Track
from models.server_state import get_server_state, get_mood
from models.user_profile import get_user_summary
from personality.prompts import build_chat_prompt, build_recommendation_prompt
from personality.responses import (
    pick_random,
    RATE_LIMIT_MESSAGES,
    ERROR_MESSAGES,
    AI_EMPTY_RESPONSE,
    AUTO_QUEUE_ANNOUNCE,
    AUTO_QUEUE_CAP_REACHED,
    AUTO_QUEUE_IGNORED,
)
from personality.seasonal import get_seasonal_context
from services.gemini import GeminiRateLimitError, GeminiAPIError
from utils.logger import log


class AICog(commands.Cog):
    """Handles /ask and AI-powered auto-queue."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def gemini(self):
        return self.bot.gemini_service

    @property
    def db(self):
        return self.bot.db

    # ──────────────────────────── /ask ────────────────────────────

    @app_commands.command(name="ask", description="Ask Dexter anything")
    @app_commands.describe(question="Your question")
    @app_commands.checks.cooldown(1, config.ASK_COOLDOWN_SECONDS)
    async def ask(self, interaction: discord.Interaction, question: str) -> None:
        await interaction.response.defer()

        try:
            # Gather context
            mood = await get_mood(self.db)
            user_summary = await get_user_summary(self.db, str(interaction.user.id))
            seasonal = get_seasonal_context()
            conversation = self.bot.message_buffer.get_gemini_history(interaction.channel.id)

            # Add the current question to conversation
            conversation.append({
                "role": "user",
                "content": f"{interaction.user.display_name}: {question}",
            })

            # Build prompt and call Gemini
            system_prompt = build_chat_prompt(mood, user_summary, seasonal)
            response = await self.gemini.chat(system_prompt, conversation, priority=1)

            if not response:
                response = pick_random(AI_EMPTY_RESPONSE)

            await interaction.followup.send(response)

            # Add bot response to buffer
            self.bot.message_buffer.add(
                channel_id=interaction.channel.id,
                role="model",
                author="Dexter",
                content=response,
            )

            # Update stats
            await increment_daily_stat(self.db, "total_commands")
            await increment_daily_stat(self.db, "total_ai_queries")

        except GeminiRateLimitError:
            await interaction.followup.send(pick_random(RATE_LIMIT_MESSAGES))
        except GeminiAPIError as e:
            log.error(f"/ask Gemini error: {e}")
            await interaction.followup.send(pick_random(ERROR_MESSAGES))
            await self._log_error("Gemini API Error", str(e))

    # ──────────────────────────── AUTO-QUEUE ────────────────────────────

    async def try_auto_queue(self, guild: discord.Guild) -> None:
        """Attempt to auto-queue songs. Called by music cog when queue empties."""
        server_state = get_server_state(self.bot.server_states, guild.id)

        if server_state.auto_queue_rounds >= config.AUTO_QUEUE_MAX_ROUNDS:
            # Cap reached
            channel = self._get_text_channel(guild)
            if channel:
                await channel.send(pick_random(AUTO_QUEUE_CAP_REACHED))
            return

        try:
            # Get recent songs for context
            recent = await get_recent_songs(self.db, guild_id=str(guild.id), limit=10)
            if not recent:
                return

            # Ask Gemini for recommendations
            prompt = build_recommendation_prompt(recent)
            response = await self.gemini.chat(prompt, [], priority=2)

            if not response:
                return

            # Parse JSON
            suggestions = self._parse_suggestions(response)
            if not suggestions:
                log.warning("Auto-queue: failed to parse suggestions")
                return

            # Search YouTube and queue
            music_cog = self.bot.cogs.get("MusicCog")
            if not music_cog:
                return

            queue = music_cog.get_queue(guild.id)
            tracks_added = []

            for suggestion in suggestions[: config.AUTO_QUEUE_SONGS_PER_ROUND]:
                search_query = f"{suggestion['title']} {suggestion['artist']}"
                results = await self.bot.youtube_service.async_search(search_query, count=1)
                if not results:
                    continue

                result = results[0]
                try:
                    data = await self.bot.youtube_service.async_extract(result["url"])
                except Exception:
                    continue

                if data["duration"] > config.MAX_SONG_DURATION_SECONDS:
                    continue

                track = Track(
                    video_id=data["video_id"],
                    title=data["title"],
                    artist=data.get("artist"),
                    url=data["url"],
                    duration_seconds=data["duration"],
                    requested_by=self.bot.user.id,
                    was_auto_queued=True,
                    thumbnail=data.get("thumbnail"),
                )
                queue.add(track)
                tracks_added.append(track)

            if not tracks_added:
                return

            # Start playback
            voice_client = guild.voice_client
            if voice_client and not queue.is_playing:
                queue.current_index = len(queue.tracks) - len(tracks_added)
                await music_cog._play_track(guild, queue.get_current())

            # Post announcement
            channel = self._get_text_channel(guild)
            if channel:
                msg = pick_random(AUTO_QUEUE_ANNOUNCE)
                # Add "ignored" memory commentary
                prev = server_state.auto_queue_results
                if prev["skipped"] > 0 and prev["played"] + prev["skipped"] > 0:
                    msg = pick_random(AUTO_QUEUE_IGNORED) + "\n\n" + msg
                await channel.send(msg)

            server_state.auto_queue_rounds += 1
            server_state.auto_queue_results = {"played": 0, "skipped": 0}

        except GeminiRateLimitError:
            log.info("Auto-queue: rate limited, skipping")
        except GeminiAPIError as e:
            log.error(f"Auto-queue Gemini error: {e}")
        except Exception as e:
            log.error(f"Auto-queue unexpected error: {e}", exc_info=True)

    def _parse_suggestions(self, response: str) -> list[dict] | None:
        """Parse Gemini's JSON response into song suggestions."""
        # Strip markdown code fences if present
        cleaned = response.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            data = json.loads(cleaned)
            if isinstance(data, list) and all(
                isinstance(item, dict) and "title" in item and "artist" in item
                for item in data
            ):
                return data
        except (json.JSONDecodeError, TypeError):
            log.warning(f"Auto-queue JSON parse failed: {response[:200]}")
        return None

    def _get_text_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """Get the text channel for posting (reuses music cog's channel tracking)."""
        music_cog = self.bot.cogs.get("MusicCog")
        if music_cog:
            return music_cog._get_text_channel(guild)
        return None

    async def _log_error(self, title: str, details: str) -> None:
        """Log an error to the Discord error channel if configured."""
        if hasattr(self.bot, "log_to_discord"):
            embed = discord.Embed(title=title, description=details, color=0xFF0000)
            await self.bot.log_to_discord(embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AICog(bot))
```

- [ ] **Step 2: Verify AI cog parses JSON correctly (unit test for _parse_suggestions)**

Add to a new test file `tests/test_ai_helpers.py`:

```python
"""Tests for AI cog helper functions."""

from cogs.ai import AICog


class TestParseSuggestions:
    def setup_method(self):
        self.cog = AICog.__new__(AICog)

    def test_parses_valid_json(self):
        response = '[{"title": "Song", "artist": "Artist"}]'
        result = self.cog._parse_suggestions(response)
        assert result == [{"title": "Song", "artist": "Artist"}]

    def test_parses_markdown_wrapped(self):
        response = '```json\n[{"title": "Song", "artist": "Artist"}]\n```'
        result = self.cog._parse_suggestions(response)
        assert result is not None
        assert result[0]["title"] == "Song"

    def test_returns_none_for_invalid(self):
        result = self.cog._parse_suggestions("not json at all")
        assert result is None

    def test_returns_none_for_missing_fields(self):
        result = self.cog._parse_suggestions('[{"title": "Song"}]')
        assert result is None

    def test_parses_three_suggestions(self):
        response = '[{"title": "A", "artist": "1"}, {"title": "B", "artist": "2"}, {"title": "C", "artist": "3"}]'
        result = self.cog._parse_suggestions(response)
        assert len(result) == 3
```

- [ ] **Step 3: Run the helper tests**

Run: `python -m pytest tests/test_ai_helpers.py -v`

Expected: All 5 tests PASS.

---

## Task 12: Bot.py Wiring (Stage 1)

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Add Stage 1 service and cog wiring to bot.py**

In `bot.py`, add imports at the top (after existing imports):

```python
from models.message_buffer import MessageBuffer
from models.server_state import ServerState
```

In the `on_ready()` function, add after the existing services section:

```python
    # Message buffer
    bot.message_buffer = MessageBuffer()

    # Server states (per-guild runtime state)
    bot.server_states: dict[int, ServerState] = {}

    # Gemini service (only if API key is available)
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        from services.gemini import GeminiService
        bot.gemini_service = GeminiService(api_key=gemini_key)
        log.info("Gemini service initialized")
    else:
        log.warning("GEMINI_API_KEY not set — AI features disabled")
```

In the cog loading section, add after the existing `load_extension` calls:

```python
    await bot.load_extension("cogs.events")
    if hasattr(bot, "gemini_service"):
        await bot.load_extension("cogs.ai")
```

- [ ] **Step 2: Run all tests to verify no regressions**

Run: `python -m pytest tests/ -v`

Expected: All tests pass.

- [ ] **Step 3: Manual smoke test — start bot and test /ask**

Run: `python bot.py`

Test in Discord:
1. `/ask what is your name` — should get a sarcastic response from Dexter
2. `/ask what music have I been listening to` — should reference user's history (or say no data)
3. Rapid `/ask` — should hit cooldown after 5s

---

# Stage 2: Image Generation

## Task 13: Imagine Cog

**Files:**
- Create: `cogs/imagine.py`
- Modify: `bot.py` (add cog loading)

- [ ] **Step 1: Create the imagine cog**

Create `cogs/imagine.py`:

```python
"""Image generation slash command."""

from __future__ import annotations

import io
import random

import discord
from discord import app_commands
from discord.ext import commands

import config
from database import get_images_today, log_image, increment_daily_stat
from personality.responses import (
    pick_random,
    IMAGE_REFUSAL_MESSAGES,
    IMAGE_CAP_MESSAGES,
    RATE_LIMIT_MESSAGES,
    ERROR_MESSAGES,
)
from services.gemini import GeminiRateLimitError, GeminiAPIError
from utils.logger import log


IMAGE_CAPTIONS: list[str] = [
    "here. i made this. you're welcome.",
    "one ai-generated masterpiece, as requested.",
    "i can't believe i'm doing art for you.",
    "behold. or don't. i don't care.",
    "this is what my processing power is being used for.",
]


class ImagineCog(commands.Cog):
    """Handles the /imagine command."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def gemini(self):
        return self.bot.gemini_service

    @property
    def db(self):
        return self.bot.db

    @app_commands.command(name="imagine", description="Generate an image")
    @app_commands.describe(prompt="What to generate")
    @app_commands.checks.cooldown(1, config.IMAGINE_COOLDOWN_SECONDS)
    async def imagine(self, interaction: discord.Interaction, prompt: str) -> None:
        # Check daily cap
        images_today = await get_images_today(self.db, user_id=str(interaction.user.id))
        if images_today >= config.MAX_IMAGES_PER_USER_PER_DAY:
            return await interaction.response.send_message(
                pick_random(IMAGE_CAP_MESSAGES), ephemeral=True
            )

        await interaction.response.defer()

        try:
            image_bytes = await self.gemini.generate_image(prompt, priority=1)

            if image_bytes is None:
                await interaction.followup.send(pick_random(IMAGE_REFUSAL_MESSAGES))
                return

            # Send image as a Discord file
            file = discord.File(
                io.BytesIO(image_bytes),
                filename="dexter_imagine.jpg",
            )
            caption = random.choice(IMAGE_CAPTIONS)
            await interaction.followup.send(content=caption, file=file)

            # Log
            await log_image(
                self.db,
                guild_id=str(interaction.guild.id),
                user_id=str(interaction.user.id),
                prompt=prompt,
            )
            await increment_daily_stat(self.db, "total_images_generated")
            await increment_daily_stat(self.db, "total_commands")

        except GeminiRateLimitError:
            await interaction.followup.send(pick_random(RATE_LIMIT_MESSAGES))
        except GeminiAPIError as e:
            log.error(f"/imagine Gemini error: {e}")
            await interaction.followup.send(pick_random(ERROR_MESSAGES))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ImagineCog(bot))
```

- [ ] **Step 2: Add imagine cog loading to bot.py**

In `bot.py on_ready()`, in the cog loading section, add after the `cogs.ai` line:

```python
        await bot.load_extension("cogs.imagine")
```

(This should be inside the `if hasattr(bot, "gemini_service"):` block.)

- [ ] **Step 3: Manual smoke test — /imagine**

Run: `python bot.py`

Test in Discord:
1. `/imagine a cat wearing a top hat` — should get image + sarcastic caption
2. `/imagine` with inappropriate prompt — should get refusal message
3. Rapid `/imagine` — should hit 30s cooldown

---

# Stage 3: Infrastructure

## Task 14: Global Error Handler + Error Log Channel

**Files:**
- Modify: `utils/logger.py`
- Modify: `bot.py`

- [ ] **Step 1: Add log_to_discord to utils/logger.py**

Add to the bottom of `utils/logger.py`:

```python
async def log_to_discord(bot, embed: discord.Embed) -> None:
    """Send an error embed to the Discord error log channel.

    Silently skips if ERROR_LOG_CHANNEL_ID is not set or channel not found.
    """
    import config

    if not config.ERROR_LOG_CHANNEL_ID:
        return
    channel = bot.get_channel(config.ERROR_LOG_CHANNEL_ID)
    if not channel:
        return
    try:
        await channel.send(embed=embed)
    except Exception as e:
        log.error(f"Failed to log to Discord error channel: {e}")
```

Add `import discord` at the top of `utils/logger.py`.

- [ ] **Step 2: Add global error handler and log_to_discord to bot.py**

Add after the `on_close` event in `bot.py`:

```python
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """Global error handler for all slash commands."""
    if isinstance(error, app_commands.CommandOnCooldown):
        if not interaction.response.is_done():
            await interaction.response.send_message(
                f"slow down. try again in {error.retry_after:.0f}s.",
                ephemeral=True,
            )
        return

    # Log unexpected errors
    log.error(f"Unhandled command error: {error}", exc_info=error)
    from utils.logger import log_to_discord
    embed = discord.Embed(
        title="Unhandled Command Error",
        description=f"Command: {interaction.command.name if interaction.command else 'unknown'}\n"
                    f"Error: {error}",
        color=0xFF0000,
    )
    await log_to_discord(bot, embed)

    if not interaction.response.is_done():
        await interaction.response.send_message(
            "something broke and it wasn't my fault. probably.",
            ephemeral=True,
        )
    else:
        await interaction.followup.send(
            "something broke and it wasn't my fault. probably.",
        )
```

Also add `log_to_discord` as a bot attribute in `on_ready()` so cogs can access it:

```python
    from utils.logger import log_to_discord as _log_to_discord
    bot.log_to_discord = lambda embed: _log_to_discord(bot, embed)
```

- [ ] **Step 3: Run all tests to verify no regressions**

Run: `python -m pytest tests/ -v`

Expected: All tests pass.

---

## Task 15: Music Cog Changes (Skip Tracking + Auto-Queue Trigger)

**Files:**
- Modify: `cogs/music.py`

- [ ] **Step 1: Add skip tracking to the /skip command**

In `cogs/music.py`, modify the `skip` command. After the line `next_track = queue.skip()`, add auto-queued skip tracking before the response:

```python
    @app_commands.command(name="skip", description="Skip to the next song")
    @app_commands.checks.cooldown(1, config.SKIP_COOLDOWN_SECONDS)
    async def skip(self, interaction: discord.Interaction) -> None:
        queue = self.get_queue(interaction.guild.id)
        voice_client = interaction.guild.voice_client

        if not voice_client or not queue.is_playing:
            return await interaction.response.send_message(
                embed=embeds.error("Nothing is playing."), ephemeral=True
            )

        # Track skipped auto-queued songs
        current = queue.get_current()
        if current and current.was_auto_queued:
            from database import mark_song_skipped
            from models.server_state import get_server_state
            await mark_song_skipped(self.db, guild_id=str(interaction.guild.id), url=current.url)
            if hasattr(self.bot, "server_states"):
                state = get_server_state(self.bot.server_states, interaction.guild.id)
                state.auto_queue_results["skipped"] += 1

        next_track = queue.skip()
        if next_track:
            await interaction.response.send_message(f"Skipped to **{next_track.title}**")
            asyncio.create_task(self._play_track(interaction.guild, next_track))
        else:
            queue.is_playing = False
            voice_client.stop()
            await interaction.response.send_message("End of queue.")
```

- [ ] **Step 2: Add auto-queue round reset to /play**

In the `play` command, add after `queue._text_channel_id = interaction.channel.id`:

```python
        # Reset auto-queue rounds when a human queues a song
        if hasattr(self.bot, "server_states"):
            from models.server_state import get_server_state
            state = get_server_state(self.bot.server_states, interaction.guild.id)
            state.reset_auto_queue()
```

- [ ] **Step 3: Add auto-queue trigger to _on_track_end**

Modify `_on_track_end` to trigger auto-queue when the queue is exhausted:

```python
    async def _on_track_end(self, guild: discord.Guild) -> None:
        """Called when a track finishes naturally. Handles advance/loop logic."""
        queue = self.get_queue(guild.id)

        if not queue.is_playing:
            return

        # Track auto-queued song that played fully (not skipped)
        current = queue.get_current()
        if current and current.was_auto_queued and hasattr(self.bot, "server_states"):
            from models.server_state import get_server_state
            state = get_server_state(self.bot.server_states, guild.id)
            state.auto_queue_results["played"] += 1

        next_track = queue.advance()
        if next_track:
            await self._play_track(guild, next_track)
            channel = self._get_text_channel(guild)
            if channel:
                embed = embeds.now_playing(next_track, queue)
                if queue._now_playing_message_id:
                    try:
                        msg = await channel.fetch_message(queue._now_playing_message_id)
                        await msg.edit(embed=embed)
                        return
                    except Exception:
                        pass
                msg = await channel.send(embed=embed)
                queue._now_playing_message_id = msg.id
        else:
            # Queue exhausted — try auto-queue before stopping
            voice_client = guild.voice_client
            if voice_client and voice_client.channel:
                human_members = [m for m in voice_client.channel.members if not m.bot]
                if human_members:
                    ai_cog = self.bot.cogs.get("AICog")
                    if ai_cog:
                        asyncio.create_task(ai_cog.try_auto_queue(guild))
                        return  # Don't set is_playing = False yet; auto-queue will handle it

            queue.is_playing = False
```

- [ ] **Step 4: Run all tests to verify no regressions**

Run: `python -m pytest tests/ -v`

Expected: All tests pass.

---

## Task 16: Help Cog Update

**Files:**
- Modify: `cogs/help.py`

- [ ] **Step 1: Add /ask and /imagine to help text**

In `cogs/help.py`, add to the `COMMANDS_INFO` list:

```python
    ("/ask <question>", "Ask Dexter anything (AI-powered)"),
    ("/imagine <prompt>", "Generate an image"),
```

- [ ] **Step 2: Run all tests to ensure nothing broke**

Run: `python -m pytest tests/ -v`

Expected: All tests pass.

- [ ] **Step 3: Final manual smoke test**

Run: `python bot.py`

Full test checklist:
1. `/help` — should show /ask and /imagine
2. `/ask what is your name` — personality response
3. `/ask` rapid fire — cooldown message "slow down..."
4. `/imagine a sunset over mountains` — image + caption
5. `/imagine` inappropriate prompt — refusal message
6. Play 3-4 songs, let queue empty while in voice — auto-queue should fire
7. `/play` a song manually — should reset auto-queue counter
8. Skip all auto-queued songs — "ignored" memory on next auto-queue round
9. Let auto-queue run 3 rounds — cap message, stops auto-queuing
10. Check logs directory for logged errors

---

# Post-Implementation Verification

After all tasks are complete, run the full test suite:

```
python -m pytest tests/ -v
```

Expected test files and approximate counts:
- `tests/test_formatters.py` — Phase 1 (existing)
- `tests/test_queue.py` — Phase 1 (existing)
- `tests/test_database.py` — Phase 1 (existing)
- `tests/test_youtube.py` — Phase 1 (existing)
- `tests/test_audio.py` — Phase 1 (existing)
- `tests/test_seasonal.py` — 6 tests
- `tests/test_prompts.py` — 10 tests
- `tests/test_responses.py` — 9 tests
- `tests/test_message_buffer.py` — 8 tests
- `tests/test_database_phase2.py` — 11 tests
- `tests/test_user_profile.py` — 5 tests
- `tests/test_server_state.py` — 9 tests
- `tests/test_rate_limiter.py` — 4 tests
- `tests/test_gemini.py` — 3 tests
- `tests/test_ai_helpers.py` — 5 tests

**Total: ~70 new tests + existing Phase 1 tests**
