---
phase: 12-richer-music-ux
plan: "03"
subsystem: services/lyrics
tags: [lyrics, lrclib, fallback, tdd, pure-helper]
dependency_graph:
  requires: []
  provides: [strip_lrc_headers, _get_lrclib, LRCLIB-fallback-chain]
  affects: [services/lyrics.py, tests/test_lyrics_lrclib.py]
tech_stack:
  added: []
  patterns: [aiohttp-json-fetch, pure-helper-tdd, regex-multiline]
key_files:
  created:
    - tests/test_lyrics_lrclib.py
  modified:
    - services/lyrics.py
decisions:
  - "Use /api/search (not /api/get) — robust to missing duration; returns relevance-sorted array"
  - "strip_lrc_headers runs BEFORE sanitize_lyrics — sanitize only handles HTML/@mentions, not LRC lines (Pitfall 1)"
  - "User-Agent 'Dexter/1.2 (Discord music bot)' sent to satisfy LRCLIB assumption A1"
  - "min 50-char cleaned-lyrics gate mirrors AZLyrics short-content guard"
metrics:
  duration_seconds: 300
  completed_date: "2026-06-30"
  tasks_completed: 2
  files_modified: 2
---

# Phase 12 Plan 03: LRCLIB Third Lyrics Fallback Summary

**One-liner:** LRCLIB /api/search third fallback with LRC header stripping via strip_lrc_headers pure helper.

## What Was Built

Added LRCLIB (`lrclib.net`) as a third lyrics fallback to `LyricsService`, completing the chain
Genius → AZLyrics → LRCLIB. The implementation introduces two artifacts:

1. `strip_lrc_headers(text: str) -> str` — a module-level pure helper that removes `[ti:]/[ar:]/[al:]/[by:]/[offset:]/[length:]/[re:]/[ve:]` lines using a MULTILINE regex, without touching mid-line brackets. Runs before `sanitize_lyrics()`.

2. `LyricsService._get_lrclib(title, artist)` — mirrors `_get_azlyrics` exactly: `aiohttp.ClientSession`, `ClientTimeout(total=10)`, 500,000-byte response cap, `try/except Exception → None`. Sends `track_name` + `artist_name` as URL-encoded `params=` to `https://lrclib.net/api/search`, iterates results skipping instrumental/empty entries, strips LRC headers, and returns `sanitize_lyrics(cleaned)`.

`get_lyrics` updated: the AZLyrics branch now checks for truthiness before returning, and falls through to `_get_lrclib` when AZLyrics returns None.

## Tasks

| # | Name | Commit | Key Files |
|---|------|--------|-----------|
| 1 | strip_lrc_headers pure helper + TDD tests | e70d3a4 | services/lyrics.py, tests/test_lyrics_lrclib.py |
| 2 | _get_lrclib fetch + chain wiring + mocked tests | c5eacdf | services/lyrics.py, tests/test_lyrics_lrclib.py |

## Tests

- 16 tests in `tests/test_lyrics_lrclib.py` (7 strip_lrc_headers unit + 6 _get_lrclib mocked + 3 chain-wiring)
- Full suite: 586 passed, 93 skipped — no regressions
- TDD: RED phase confirmed `ImportError` before implementation; GREEN phase all tests pass

## Verification Results

- `python -m pytest tests/test_lyrics_lrclib.py -x` — 16 passed
- `python -m pytest tests/ -x` — 586 passed, 0 failed
- `python -c "import services.lyrics"` — imports clean
- `python -c "import ast; ast.parse(open('services/lyrics.py',encoding='utf-8').read())"` — exits 0
- `grep _get_lrclib services/lyrics.py` — present at definition (line 350) and awaited in `get_lyrics` (line 277)
- Manual live test: deferred to live bot run (tracked in VALIDATION.md)

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. `_get_lrclib` is fully wired with live HTTP logic; `strip_lrc_headers` does real regex processing.

## Self-Check: PASSED

- `services/lyrics.py` exists and modified: FOUND
- `tests/test_lyrics_lrclib.py` created: FOUND
- Commit e70d3a4 (Task 1): FOUND
- Commit c5eacdf (Task 2): FOUND
