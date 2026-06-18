---
phase: "07-player-ux-filters"
plan: "04"
subsystem: "library-playlists"
tags: [playlists, library, jsonb, asyncpg, discord-commands, phase7, tdd]
dependency_graph:
  requires:
    - database.SCHEMA_SQL (guild_queues JSONB table as pattern reference)
    - database.asyncpg helper convention ($N params, pool.acquire, json.dumps/loads)
    - config.PLAYLISTS_MAX_PER_USER + PLAYLIST_NAME_MAX_LENGTH (Plan 01)
    - personality.responses PLAYLIST_SAVED/LOADED/NOT_FOUND/CAP_HIT (Plan 01)
    - models.queue.Track.to_dict / Track.from_dict / QueueFullError
    - cogs.library.LibraryCog (Plan 03 — extended here)
    - MusicCog.get_queue / MusicCog._play_track
    - utils.embeds.now_playing
    - cogs.music.NowPlayingView
  provides:
    - database.user_playlists schema + CREATE INDEX idx_playlists_user
    - database.save_playlist / get_playlist / list_playlists / delete_playlist / count_playlists
    - cogs.library.LibraryCog /playlist group (save/load/list/delete)
    - tests/test_database_phase7.py playlist cases (20 new live-DB tests)
  affects:
    - database.py (SCHEMA_SQL + 5 new helpers)
    - cogs/library.py (playlist group + 4 subcommands + extended imports)
    - tests/test_database_phase7.py (20 new tests, now 34 total)
tech_stack:
  added: []
  patterns:
    - TDD RED/GREEN: failing tests committed before implementation
    - asyncpg JSONB upsert (INSERT ... ON CONFLICT DO UPDATE SET snapshot+updated_at)
    - json.dumps snapshot list → $N::jsonb param; json.loads normalisation on read
    - jsonb_array_length(snapshot) for track_count in list_playlists
    - delete_playlist returns bool via asyncpg execute() status string ("DELETE 1"/"DELETE 0")
    - app_commands.Group class attribute on LibraryCog for /playlist subcommands
    - Upsert-exempt cap: count_playlists only blocks genuinely new names (get_playlist None check)
    - Append-on-load with QueueFullError truncation reporting (D-26)
key_files:
  created: []
  modified:
    - database.py
    - cogs/library.py
    - tests/test_database_phase7.py
decisions:
  - "Upsert-exempt cap check: save_playlist cap only fires when get_playlist returns None (new name) — avoids blocking a re-save of an existing playlist that would not expand count"
  - "delete_playlist returns bool via parse of asyncpg execute() status string ('DELETE N') — no extra SELECT needed, avoids race window"
  - "list_playlists uses jsonb_array_length(snapshot) for track_count — eliminates a separate COUNT query and keeps the metadata fetch atomic"
  - "playlist load idle-start: queue.current_index set to len(tracks)-added (first newly added track) before _play_track — mirrors queue_persistence restore pattern"
  - "TDD: RED commit (test(07-04)) before GREEN commit (feat(07-04)) preserves gate sequence per plan tdd=true requirement"
metrics:
  duration: "~15 min"
  completed: "2026-06-19"
  tasks_completed: 2
  files_modified: 3
---

# Phase 7 Plan 04: Named Playlists Summary

**One-liner:** user_playlists JSONB table (PK user_id+name, upsert-on-name-clash) with save/get/list/delete/count asyncpg helpers (live-DB TDD tested) and a /playlist save|load|list|delete app_commands.Group on LibraryCog.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 RED | Failing tests for user_playlists helpers | 45d5c0c | tests/test_database_phase7.py |
| 1 GREEN | user_playlists schema + 5 helpers | 628cda1 | database.py |
| 2 | /playlist group on LibraryCog | a32bf0f | cogs/library.py |

## What Was Built

### Task 1 — user_playlists schema + helpers (TDD)

**SCHEMA_SQL additions:**
- `user_playlists` table: `PRIMARY KEY (user_id, name)`, `snapshot JSONB NOT NULL`, `created_at/updated_at TIMESTAMPTZ DEFAULT now()`
- `idx_playlists_user ON user_playlists(user_id, updated_at DESC)` index

**asyncpg helpers (5):**
- `save_playlist(pool, *, user_id, name, snapshot: list[dict])` — INSERT ... ON CONFLICT DO UPDATE SET snapshot+updated_at; json.dumps the list (T-07-04-01)
- `get_playlist(pool, *, user_id, name) -> list[dict] | None` — fetchrow + json.loads normalisation (asyncpg JSONB may return str or list)
- `list_playlists(pool, *, user_id) -> list[dict]` — jsonb_array_length for track_count, ORDER BY updated_at DESC (D-24)
- `delete_playlist(pool, *, user_id, name) -> bool` — DELETE, bool from execute() status string "DELETE N" (D-28)
- `count_playlists(pool, *, user_id) -> int` — COUNT for cap enforcement (D-28, T-07-04-03)

**20 new live-DB integration tests** across 5 test classes (34 total in file):
- TestUserPlaylistsSchema: table exists, correct columns
- TestSavePlaylist: insert, upsert on name clash, cross-user isolation
- TestGetPlaylist: missing returns None, JSONB round-trip (Track.from_dict → to_dict), correct name fetch
- TestListPlaylists: empty list, metadata rows (name/track_count/updated_at), newest-first, own-only
- TestDeletePlaylist: removes row (True), missing (False), target-only, cross-user isolation
- TestCountPlaylists: zero for new user, increments, upsert does not increment, per-user isolation

Tests collect cleanly without live Postgres (autonomous gate); require dexter_test DB for full run.

### Task 2 — /playlist group on LibraryCog

**cogs/library.py — playlist = app_commands.Group (class attribute on LibraryCog):**

`/playlist save <name>`:
- Guards: empty queue, name > PLAYLIST_NAME_MAX_LENGTH (60), PLAYLISTS_MAX_PER_USER cap (25)
- Upsert-exempt cap: only blocks when get_playlist returns None (genuinely new name, D-27)
- `snapshot=[t.to_dict() for t in queue.tracks]` → save_playlist upsert
- Ephemeral PLAYLIST_SAVED with track count (T-07-04-01, T-07-04-02, T-07-04-03)

`/playlist load <name>`:
- get_playlist → PLAYLIST_NOT_FOUND if missing
- Voice channel guard (must be in VC to load)
- defer() immediately; rebuild Tracks via Track.from_dict with requested_by=user.id
- Append via queue.add() catching QueueFullError for truncation count (D-26)
- Persist queue state via queue_persistence if available
- If idle: set current_index to first newly added track, _play_track + NowPlayingView embed
- Ephemeral PLAYLIST_LOADED summary with track count + truncation notice if any

`/playlist list`:
- list_playlists → empty guard
- Ephemeral embed: each playlist as a field (name, track count, relative updated timestamp)

`/playlist delete <name>`:
- delete_playlist → bool; PLAYLIST_NOT_FOUND if False
- Ephemeral confirmation on success

All ops keyed on `str(interaction.user.id)` (T-07-04-02).

## Verification Results

```
python -c "import ast; src=open('cogs/library.py',encoding='utf-8').read(); assert 'app_commands.Group' in src and 'name=\"playlist\"' in src; print('OK')"
OK

python -c "import ast; ast.parse(open('cogs/library.py',encoding='utf-8').read()); ast.parse(open('database.py',encoding='utf-8').read()); print('syntax OK')"
syntax OK

pytest tests/test_database_phase7.py --collect-only -q
34 tests collected in 0.07s

pytest tests/test_queue.py tests/test_formatters.py tests/test_audio.py tests/test_responses.py tests/test_streak.py tests/test_config.py -x -q
97 passed, 1 warning in 0.17s
```

Human-check gates (require a running bot with Postgres):
- Queue 3 songs → /playlist save chill → ephemeral saved (3 tracks, "chill")
- Clear queue → /playlist load chill → 3 songs appended; playback starts if idle
- /playlist save chill again → upserts (overwrite); count stays at 1
- /playlist list → shows "chill" with track count + relative timestamp
- /playlist delete chill → ephemeral confirmation; gone from list
- /playlist load ghostname → ephemeral PLAYLIST_NOT_FOUND
- Save 25 playlists → 26th save (new name) → PLAYLIST_CAP_HIT; re-save existing name still works
- Queue 500 songs → /playlist save big → saved; /playlist load big into a near-full queue → truncation notice

## Deviations from Plan

None — plan executed exactly as written.

## Threat Model Compliance

| Threat | Status |
|--------|--------|
| T-07-04-01 (SQL injection / JSONB) | Mitigated — all 5 helpers use $N-parameterised asyncpg queries; snapshot via json.dumps as $N::jsonb |
| T-07-04-02 (cross-user playlists) | Mitigated — every save/load/list/delete keyed on str(interaction.user.id); no cross-user reads |
| T-07-04-03 (DoS: oversized snapshot / unbounded playlists) | Mitigated — snapshot bounded by live queue (MAX_QUEUE_SIZE_PER_GUILD=500); load truncates to cap; PLAYLISTS_MAX_PER_USER=25 + PLAYLIST_NAME_MAX_LENGTH=60 enforced on save |
| T-07-04-04 (stale track URLs) | Accepted — dead URLs fail through existing AudioService skip-and-continue path |
| T-07-04-SC (new pip deps) | None — no new dependencies |

## Known Stubs

None. All commands fully wired. Remaining human-verify gates require a running bot with live Postgres.

## Threat Flags

None. No new network endpoints, auth paths, file access patterns, or schema changes beyond what the plan's threat model covers.

## TDD Gate Compliance

- RED gate: commit `45d5c0c` — `test(07-04): add failing tests for user_playlists helpers (RED)`
- GREEN gate: commit `628cda1` — `feat(07-04): user_playlists schema + save/get/list/delete/count helpers (GREEN)`
- Both gates present in git log.

## Self-Check: PASSED

- database.py: `CREATE TABLE IF NOT EXISTS user_playlists` — FOUND
- database.py: `save_playlist`, `get_playlist`, `list_playlists`, `delete_playlist`, `count_playlists` — FOUND
- cogs/library.py: `app_commands.Group` + `name="playlist"` — FOUND
- cogs/library.py: `playlist_save`, `playlist_load`, `playlist_list`, `playlist_delete` — FOUND
- tests/test_database_phase7.py: `user_playlists` — FOUND
- tests/test_database_phase7.py: 34 tests collected — VERIFIED
- Commits 45d5c0c, 628cda1, a32bf0f — all in git log
