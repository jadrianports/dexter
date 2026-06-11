---
phase: 03-alive
plan: 03-03
subsystem: lyrics
tags: [lyricsgenius, beautifulsoup4, aiohttp, lyrics, genius, azlyrics, async, tdd]

# Dependency graph
requires:
  - phase: 03-alive/03-01
    provides: config constants LYRICS_PAGE_SIZE, LYRICS_COOLDOWN_SECONDS already in config.py

provides:
  - services/lyrics.py: LyricsService(genius_token) with async get_lyrics + pure helpers
  - Pure helpers: build_genius_search_query, build_azlyrics_url, chunk_lyrics, sanitize_lyrics, extract_azlyrics
  - tests/test_lyrics.py: 36 offline unit tests for pure helpers + LyricsService init/fallback

affects:
  - 03-05 (wires /lyrics command using bot.lyrics_service)
  - 03-04 (no direct dependency, but same Wave 1)

# Tech tracking
tech-stack:
  added:
    - lyricsgenius 3.12.2 (Genius search + scrape via asyncio.to_thread)
    - beautifulsoup4 4.15.0 (AZLyrics HTML extraction + sanitize_lyrics)
    - aiohttp 3.13.5 (already installed; now pinned in requirements.txt)
    - tzdata 2026.2 (already installed + in requirements.txt from prior task)
  patterns:
    - asyncio.to_thread wrapping synchronous library calls (non-blocking Genius)
    - aiohttp.ClientTimeout + byte-cap DoS guard pattern for untrusted HTTP fetches
    - BeautifulSoup.get_text + zero-width-space mention neutralization (defense-in-depth)
    - build_azlyrics_url: re.sub([^a-z0-9]) strips all non-alphanum (path-traversal mitigation)
    - Pure helper functions in service module for unit-testability

key-files:
  created:
    - services/lyrics.py
    - tests/test_lyrics.py
  modified:
    - requirements.txt

key-decisions:
  - "lyricsgenius 3.12.2 wrapped in asyncio.to_thread (not raw HTTP) to avoid re-implementing data-lyrics-container scraping"
  - "sanitize_lyrics inserts zero-width space (U+200B) after @ to break @everyone/@here pings as defense-in-depth"
  - "chunk_lyrics default page_size reads from config.LYRICS_PAGE_SIZE (1500) not hardcoded"
  - "aiohttp already installed at 3.13.5; appended unpinned to requirements.txt to match project style"
  - "build_genius_search_query strips (feat. X)/(Remix) suffixes via regex to improve Genius hit rate"

patterns-established:
  - "Pattern: asyncio.to_thread for blocking libs — use in any future synchronous library wrapper"
  - "Pattern: 500_000-byte response cap in aiohttp fetches — apply to any untrusted HTTP endpoint"
  - "Pattern: BeautifulSoup.get_text() for lyric/HTML sanitization before Discord output"

requirements-completed: [LYRIC-01]

# Metrics
duration: 18min
completed: 2026-06-11
---

# Phase 03: Alive — Plan 03-03 Summary

**LyricsService with Genius->AZLyrics fallback, asyncio.to_thread non-blocking wrap, full sanitization pipeline, and 36 offline TDD tests**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-06-11T13:05:00Z
- **Completed:** 2026-06-11T13:23:00Z
- **Tasks:** 2 (+ supply-chain checkpoint pre-approved)
- **Files modified:** 3 (requirements.txt, services/lyrics.py [new], tests/test_lyrics.py [new])

## Accomplishments

- Installed lyricsgenius 3.12.2 and beautifulsoup4 4.15.0 into venv; appended all four deps unpinned to requirements.txt; venv import check `deps ok` confirmed
- Created `services/lyrics.py` with `LyricsService` (Genius primary -> AZLyrics fallback -> None), all STRIDE mitigations implemented (T-03-06 through T-03-09)
- 36 offline unit tests pass; full suite 243 passed, 1 known pre-existing failure (test_ytdlp_selfheal)

## Verification Results

**Deps install check:**
```
.venv/Scripts/python.exe -c "import lyricsgenius, bs4, aiohttp, zoneinfo; from zoneinfo import ZoneInfo; ZoneInfo('America/New_York'); print('deps ok')"
→ deps ok
```

**Offline test_lyrics.py:**
```
.venv/Scripts/python.exe -m pytest tests/test_lyrics.py -x --tb=short
→ 36 passed in 1.05s
```

**Full suite:**
```
.venv/Scripts/python.exe -m pytest -q
→ 1 failed (test_ytdlp_selfheal — pre-existing), 243 passed, 1 warning
```

**LyricsService('') graceful degradation:**
```
.venv/Scripts/python.exe -c "import services.lyrics; services.lyrics.LyricsService('')"
→ WARNING: GENIUS_TOKEN not set — Genius lyrics disabled  (no exception)
```

## Task Commits

Each task was committed atomically:

1. **Task 1: Pin lyrics dependencies and install** - `f91bdb3` (feat)
2. **Task 2: TDD RED — failing tests** - `e0b0774` (test)
3. **Task 2: TDD GREEN — LyricsService implementation** - `18eb9cc` (feat)

## Files Created/Modified

- `requirements.txt` — added lyricsgenius, beautifulsoup4, aiohttp (tzdata was already present)
- `services/lyrics.py` — LyricsService class + pure helpers; 228 lines
- `tests/test_lyrics.py` — 36 offline unit tests across 7 test classes; 354 lines

## Must-Haves Status

| Truth | Status |
|-------|--------|
| LyricsService.get_lyrics returns Genius lyrics when found, falls back to AZLyrics, returns None when both fail | MET — get_lyrics() chains _get_genius -> _get_azlyrics -> None |
| Genius lookup never blocks the event loop (wrapped in asyncio.to_thread) | MET — `asyncio.to_thread(self._genius.search_song, ...)` in _get_genius |
| Scraped lyrics are sanitized before reaching Discord (HTML stripped, mentions neutralized) | MET — sanitize_lyrics() runs BeautifulSoup.get_text + zero-width-space after @ |
| Pure helpers build_genius_search_query, build_azlyrics_url, chunk_lyrics are unit-tested | MET — 36 offline tests covering all pure helpers |

## Security Acceptance Criteria

| Check | Result |
|-------|--------|
| asyncio.to_thread wraps Genius sync call | CONFIRMED — line 182: `await asyncio.to_thread(self._genius.search_song, ...)` |
| build_azlyrics_url strips ALL non-alphanum (`re.sub(r"[^a-z0-9]", "", x.lower())`) | CONFIRMED — kills path traversal and @ |
| sanitize_lyrics neutralizes @everyone/@here | CONFIRMED — re.sub inserts U+200B zero-width space after @ |
| _get_azlyrics uses ClientTimeout(total=10) | CONFIRMED — line 210 |
| _get_azlyrics has 500_000-byte size cap | CONFIRMED — line 217 |
| GENIUS_TOKEN never logged or echoed | CONFIRMED — no log line references the token value; only "GENIUS_TOKEN not set" message |
| LyricsService("") initializes without raising | CONFIRMED — sets _genius=None, logs warning |

## User Setup Required

**GENIUS_TOKEN** must be set in `.env` for Genius primary lyrics lookup:

1. Go to https://genius.com/api-clients
2. Create a new API client (any name/website)
3. Copy the "Client Access Token"
4. Add to `.env`: `GENIUS_TOKEN=<your_token>`

Without this token, the service operates in AZLyrics-only mode (graceful degradation). The `/lyrics` command still works but skips the Genius lookup.

**Note:** The supply-chain checkpoint for lyricsgenius, beautifulsoup4, aiohttp, tzdata was approved by the user before execution began.

## Deviations from Plan

None — plan executed exactly as written.

The plan noted aiohttp was not installed (`✗` in RESEARCH.md environment table), but aiohttp 3.13.5 was already present in the venv from a prior dependency. The version installed differs from the researched [ASSUMED] 3.14.1 but is the current stable release — no issue. Similarly tzdata was already in requirements.txt from plan 03-01.

## Issues Encountered

None.

## Next Phase Readiness

- `services/lyrics.py` is ready for wiring into the `/lyrics` slash command (plan 03-05)
- `bot.lyrics_service = LyricsService(os.getenv("GENIUS_TOKEN"))` should be added to `bot.py` `on_ready()` per PATTERNS.md
- `chunk_lyrics` and `LyricsPageView` are used together in the `/lyrics` command (03-05 owns that)

---
*Phase: 03-alive*
*Completed: 2026-06-11*
