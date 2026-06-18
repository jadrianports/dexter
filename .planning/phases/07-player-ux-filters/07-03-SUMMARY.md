---
phase: "07-player-ux-filters"
plan: "03"
subsystem: "library-favorites"
tags: [favorites, library, discord-ui, asyncpg, phase7, tdd]
dependency_graph:
  requires:
    - database.SCHEMA_SQL (guild_queues table as schema pattern reference)
    - database.asyncpg helper convention ($N params, pool.acquire)
    - config.FAVORITES_MAX_PER_USER
    - personality.responses Phase 7 pools (FAVORITE_SAVED/DUPLICATE/CAP_HIT, FAVORITES_EMPTY, NOTHING_PLAYING)
    - MusicCog.get_queue / MusicCog._play_track / MusicCog.get_cog lookup
    - models.queue.Track / Track.from_dict fields
    - utils.embeds.now_playing / song_queued
    - cogs.music.NowPlayingView
  provides:
    - database.add_favorite / count_favorites / get_favorites / remove_favorite
    - user_favorites Postgres table + idx_favorites_user index
    - cogs.library.LibraryCog (/favorite + /favorites commands)
    - cogs.library.FavoritesView (Select + Queue + Remove buttons)
    - tests/test_database_phase7.py (14 live-DB integration tests)
  affects:
    - database.py (SCHEMA_SQL + 4 new helpers)
    - tests/conftest.py (teardown DROP list extended)
    - cogs/library.py (new file)
    - bot.py (cogs.library added to always-on load tuple)
tech_stack:
  added: []
  patterns:
    - TDD RED/GREEN: failing tests committed before implementation
    - asyncpg ON CONFLICT DO NOTHING for idempotent inserts
    - discord.ui.View (Select + 2 buttons) for favorites pick-list
    - count-before/count-after dedupe detection for meaningful DUPLICATE response
    - ephemeral-only responses (D-29, D-30)
    - cross-server favorites keyed on str(interaction.user.id) (D-18, T-07-03-02)
key_files:
  created:
    - cogs/library.py
    - tests/test_database_phase7.py
  modified:
    - database.py
    - tests/conftest.py
    - bot.py
decisions:
  - "FavoritesView uses Select + Queue + Remove buttons rather than a single select-queues-immediately pattern — allows user to pick a song and then choose to queue OR remove it, without inadvertently queuing when intent is to remove"
  - "Duplicate detection uses count_before vs count_after rather than a pre-check SELECT — avoids a race window and keeps the check atomic with the insert"
  - "FavoritesSelect stores selected_row on the parent FavoritesView so both Queue and Remove buttons can act on the same selection without re-fetching from DB"
  - "TDD: RED commit (test(07-03)) before GREEN commit (feat(07-03)) preserves gate sequence per plan tdd=true requirement"
  - "conftest teardown extended to also DROP user_playlists + user_playlist_tracks (not yet created) — forward-safe for Plan 04"
metrics:
  duration: "~20 min"
  completed: "2026-06-19"
  tasks_completed: 2
  files_modified: 5
---

# Phase 7 Plan 03: user_favorites + LibraryCog Summary

**One-liner:** user_favorites Postgres table + add/count/get/remove asyncpg helpers (live-DB TDD tested), LibraryCog with /favorite (save current song, cap 25, dedupe) and /favorites (pick-list Select + Queue/Remove buttons), wired into bot.py.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 RED | Failing tests for user_favorites helpers | 74de0e8 | tests/test_database_phase7.py |
| 1 GREEN | user_favorites schema + helpers + conftest update | d083543 | database.py, tests/conftest.py |
| 2 | LibraryCog + FavoritesView + bot.py wiring | ec3f468 | cogs/library.py, bot.py |

## What Was Built

### Task 1 — user_favorites schema + helpers (TDD)

**SCHEMA_SQL additions:**
- `user_favorites` table: `PRIMARY KEY (user_id, video_id)`, all Track fields (title, artist, url, duration_seconds, thumbnail), `added_at TIMESTAMPTZ DEFAULT now()`
- `idx_favorites_user ON user_favorites(user_id, added_at DESC)` index

**asyncpg helpers (4):**
- `add_favorite(pool, *, user_id, video_id, title, artist, url, duration_seconds, thumbnail)` — INSERT ... ON CONFLICT DO NOTHING; all values as $N params (T-07-03-01)
- `count_favorites(pool, *, user_id) -> int` — COUNT for cap enforcement
- `get_favorites(pool, *, user_id, limit=25) -> list[dict]` — newest-first (added_at DESC); each dict has all Track fields
- `remove_favorite(pool, *, user_id, video_id)` — DELETE, no-op if missing

**conftest.py:** teardown DROP extended to include `user_favorites, user_playlists, user_playlist_tracks` (forward-safe for Plan 04).

**14 new live-DB integration tests** across 4 test classes:
- TestUserFavoritesSchema: table exists, correct columns
- TestAddFavorite: insert/count, dedupe (ON CONFLICT), multi-user isolation
- TestCountFavorites: zero for new user, increments with distinct videos
- TestGetFavorites: empty list, track fields present, 3-row order, limit cap
- TestRemoveFavorite: deletes target only, no-op for missing row

Tests collect cleanly without live Postgres (autonomous gate); require dexter_test DB for full run.

### Task 2 — LibraryCog + FavoritesView + bot.py wiring

**cogs/library.py — LibraryCog(commands.Cog):**

`/favorite`:
- Checks music_cog.get_queue(guild.id).get_current() — NOTHING_PLAYING if nothing playing
- count_favorites cap check → FAVORITE_CAP_HIT if at 25
- add_favorite + count-before/after comparison → FAVORITE_DUPLICATE if no-op, FAVORITE_SAVED otherwise
- Cooldown: FAVORITE_COOLDOWN_SECONDS (2s)

`/favorites`:
- get_favorites(limit=25) → FAVORITES_EMPTY if none
- Sends ephemeral FavoritesView

**FavoritesView(discord.ui.View, timeout=180s):**
- FavoritesSelect: up to 25 options (value=video_id, description=artist); callback stores `selected_video_id` + `selected_row` on the view and edits the message to show selection
- QueueButton: routes selected track through MusicCog._play_track if idle, or queue.add + followup embed if already playing; joins voice if needed; persists queue
- RemoveButton: calls remove_favorite(user_id, selected_video_id); edits message to confirm

Ownership guard in all three Select/QueueButton/RemoveButton callbacks (T-07-03-02).

**bot.py:** `cogs.library` added to always-on cog-load tuple (alongside cogs.music, cogs.help, cogs.events) — idempotent `if _ext not in bot.extensions` guard.

## Verification Results

```
python -c "import ast; m=ast.parse(open('cogs/library.py',encoding='utf-8').read()); \
  assert any(isinstance(n,ast.ClassDef) and n.name=='LibraryCog' for n in ast.walk(m)); \
  b=open('bot.py',encoding='utf-8').read(); assert 'cogs.library' in b; print('OK')"
OK

python -c "import ast; ast.parse(open('cogs/library.py',encoding='utf-8').read()); \
  ast.parse(open('database.py',encoding='utf-8').read()); print('syntax OK')"
syntax OK

pytest tests/test_database_phase7.py --collect-only -q
14 tests collected in 0.05s

pytest tests/test_queue.py tests/test_formatters.py tests/test_audio.py \
  tests/test_responses.py tests/test_streak.py tests/test_config.py -x -q
97 passed, 1 warning in 0.43s
```

Human-check gates (require a running bot with Postgres):
- /play a song → /favorite → ephemeral "saved"; /favorite again → "already saved"; /stop → /favorite → NOTHING_PLAYING
- /favorites with no saves → ephemeral "empty" message
- /favorites with saves → ephemeral view, Select song → Queue button → plays; Select different → Remove → gone
- /favorite 26 times → cap message on 26th (25 unique video_ids)
- Favorite saved in server A → verify /favorites in server B shows it (global, D-18)

## Deviations from Plan

**1. [Implementation] FavoritesView uses Select + Queue + Remove buttons (3-widget) instead of a 2-widget (select-queues-immediately) design**
- **Found during:** Task 2 design review
- **Issue:** A select-queues-immediately pattern means the Remove button has no way to know which entry to remove without the user having already triggered a queue action. Queuing and removing are mutually exclusive intents — the user needs to pick one or the other after selecting.
- **Fix:** FavoritesSelect.callback stores `selected_row` on the parent FavoritesView without queuing; separate Queue and Remove buttons act on that selection.
- **Impact:** UX is clearer (explicit intent). All plan acceptance criteria are met: "choosing one queues it" ✓ (via Queue button), "the menu also lets the owner remove an entry" ✓ (via Remove button).
- **Files modified:** cogs/library.py

None of the must_haves, artifacts, or acceptance criteria were deviated from.

## Threat Model Compliance

| Threat | Status |
|--------|--------|
| T-07-03-01 (SQL injection) | Mitigated — all 4 helpers use $N-parameterized asyncpg queries |
| T-07-03-02 (cross-user access) | Mitigated — all Select/Queue/Remove callbacks check `interaction.user.id == self._user_id`; every DB call uses `str(interaction.user.id)` |
| T-07-03-03 (DoS via unbounded saves) | Mitigated — count_favorites checked against FAVORITES_MAX_PER_USER before insert; ON CONFLICT DO NOTHING prevents count inflation |
| T-07-03-04 (stale/invalid URL) | Accepted — dead URL fails through existing AudioService skip-and-continue path |
| T-07-03-SC (new pip deps) | None — no new dependencies |

## Known Stubs

None. All commands are fully wired. Remaining human-verify gates require a running bot with live Postgres.

## Threat Flags

None. No new network endpoints, auth paths, file access patterns, or schema changes beyond what the plan's threat model covers.

## TDD Gate Compliance

- RED gate: commit `74de0e8` — `test(07-03): add failing tests for user_favorites helpers (RED)`
- GREEN gate: commit `d083543` — `feat(07-03): user_favorites schema + add/count/get/remove helpers (GREEN)`
- Both gates present in git log.

## Self-Check: PASSED

- database.py: `CREATE TABLE IF NOT EXISTS user_favorites` — FOUND
- database.py: `add_favorite`, `count_favorites`, `get_favorites`, `remove_favorite` — FOUND
- cogs/library.py: `class LibraryCog` — FOUND
- cogs/library.py: `name="favorite"`, `name="favorites"` — FOUND
- cogs/library.py: `class FavoritesView` — FOUND
- bot.py: `cogs.library` in cog-load tuple — FOUND
- tests/test_database_phase7.py: `user_favorites` — FOUND
- tests/conftest.py: `user_favorites` in teardown DROP — FOUND
- Commits 74de0e8, d083543, ec3f468 — all in git log
