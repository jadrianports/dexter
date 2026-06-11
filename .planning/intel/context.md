# Context (DOC Intel)

> Source type: DOC. Running notes keyed by topic, appended with source attribution.
> Precedence: DOC is lowest. Where a DOC contradicts a higher-precedence SPEC, the SPEC wins (see INGEST-CONFLICTS.md).

---

## Topic: Phase 1 MVP build plan

source: docs/superpowers/plans/2026-04-12-dexter-phase1-mvp.md

Task-by-task implementation guide that operationalizes the Phase 1 design spec. Built for agentic execution (superpowers subagent-driven-development), checkbox-tracked, TDD-first for pure logic.

- File map: 14 production + 5 test files, built in task order 1–13 (scaffolding → config → logger → formatters → queue → database → youtube → audio → embeds → help cog → music cog → bot entry).
- Concrete artifacts confirmed: `requirements.txt` includes `PyNaCl` (discord.py voice) and `pytest`/`pytest-asyncio`. `config.py` paths use `pathlib.Path` (`BASE_DIR`, `AUDIO_CACHE_DIR`, `LOG_DIR`). `models/queue.py` implements `Track` dataclass + `LoopMode` enum + `MusicQueue` with `add/get_current/skip/advance/previous/shuffle/clear/upcoming`.
- `database.py` ships `init_db` (executescript on `SCHEMA_SQL`) + helpers `log_song`, `update_artist_count` (skips None artist), `update_user_profile` (upsert + increment), `increment_daily_stat` (field allow-list guard).
- `services/youtube.py`: `is_url`, `search` (ytsearchN, extract_flat), `extract` (raises ValueError on livestream / over-duration), `extract_playlist` (truncate to 50), `download` (cache-first, returns path or None), plus async wrappers via `run_in_executor`.
- `services/audio.py`: `cache_path`/`is_cached`/`get_source` (opus passthrough → download → PCM stream fallback with reconnect opts) / `cleanup_cache` (evict oldest by atime).
- Embeds: brand colors fixed; `now_playing`, `song_queued`, `queue_list` (paginated), `error`.
- Git: this plan embeds `git commit` steps per task (older convention; superseded by the user-handles-git convention noted in the Phase 2.5 plan).

## Topic: Phase 2 Personality + AI build plan

source: docs/superpowers/plans/2026-04-13-dexter-phase2-personality-ai.md

Task-by-task plan operationalizing the Phase 2 design spec. Uses `google-genai` async API (`client.aio`).

- SDK reference captured from context7: async chat via `client.aio.models.generate_content(..., config=types.GenerateContentConfig(system_instruction=...))`; async image via `client.aio.models.generate_images(...)`; multi-turn `types.Content(role=..., parts=[types.Part.from_text(...)])`; errors `google.genai.errors.APIError` with `e.code` (429 = rate limit); text via `response.text`.
- Config additions (Task 1) include image-gen model `IMAGEN_MODEL = "imagen-3.0-generate-002"`. RESOLVED 2026-06-11 — the authoritative image-gen model is `gemini-2.5-flash-image` (matches shipped `config.py:36` + Phase 1 design spec); this plan's `imagen-3.0-generate-002` value is superseded. See INGEST-CONFLICTS.md.
- New files: `personality/{seasonal,prompts,responses}.py`, `models/{message_buffer,user_profile,server_state}.py`, `services/gemini.py`, `cogs/{ai,imagine,events}.py`, plus a matching test file per module.
- Modified files: `config.py`, `requirements.txt` (+`google-genai`), `database.py` (+`mark_song_skipped`, `get_recent_songs`, `get_images_today`, `get_daily_command_count`, `log_image`), `bot.py` (wire GeminiService/MessageBuffer/server_states, global error handler, `log_to_discord`), `cogs/music.py` (auto-queue trigger, skip tracking, round reset), `cogs/help.py`.

## Topic: Phase 2.5 Hardening build plan

source: docs/superpowers/plans/2026-06-02-dexter-phase2.5-hardening.md

Task-by-task plan operationalizing the Phase 2.5 hardening spec. (Classifier confidence: medium — content signals only, one dominant; type DOC is firm, not UNKNOWN.) Convention note: **user handles all git** — no git ops baked into steps.

- 10 tasks mapped 1:1 to the spec's fixes. Stage 0 env gate → Stage 1 unsilence → Stage 2 deterministic (WAL, limit-as-int, auto-queue parse, first-run guard, playlist failure) → Stage 3 structural (FFmpeg cleanup, yt-dlp self-heal) → final regression + boot.
- New test files: `tests/test_database_hardening.py` (WAL on file DB, limit-as-int spy), `tests/test_autoqueue_parse.py` (10 malformed-JSON variants), `tests/test_ytdlp_selfheal.py` (`update_ytdlp` + download retry-after-update + throttle).
- Plan self-review records source-reading corrections: `audio.py` dropped from the unsilence list (it logs + re-raises, not silent); playlist bug reframed from "infinite thinking" to "accidental fall-through" to the single-video path.
- Concrete contracts to preserve downstream: module-level `parse_suggestions(response) -> list[dict] | None` (imported by tests + called at `ai.py:119`); `update_ytdlp() -> bool`; module state `_last_ytdlp_update` / `_UPDATE_THROTTLE_SECONDS = 3600.0`; daily `@tasks.loop(time=04:00)` `ytdlp_update` started in `on_ready`.
- The reconnect race (`cogs/music.py:~609`) is intentionally left parked for a dedicated live `/gsd:debug` session once running 24/7.

## Topic: Recent commit history alignment (reference)

source: git log (provided in environment, not an ingested doc)

The Phase 2.5 hardening plan appears partially landed already: recent commits include `feat: yt-dlp self-heal (daily update + throttled on-failure retry)`, `fix(music): explicit playlist-failure handling + ffmpeg source cleanup`, `fix(bot): guard AI cog loading during first-run sync`, and `fix(ai): parse_suggestions tolerates bracketed tokens before the array`. This corroborates the Phase 2.5 plan's contracts but is not itself a planning source.
