# Codebase Concerns

**Analysis Date:** 2026-06-01

## Tech Debt

**SQLite WAL/Locking Under Concurrent Load:**
- Issue: Each database operation calls `await db.commit()` immediately (e.g., `log_song`, `update_artist_count`, `update_user_profile`). During high traffic (many users queueing songs simultaneously), this creates multiple sequential commits that compete for locks. SQLite defaults to journal mode, not WAL, and has a 5-second timeout for locked database attempts.
- Files: `database.py` (all log/update functions), `cogs/music.py` (lines 313-314 chain 3 sequential commits per track queue)
- Impact: Track logging may fail silently on busy servers. Lost analytics data. Scale limit around 10+ concurrent song queues.
- Fix approach: Enable WAL mode in `init_db`, batch related commits (e.g., log song + update artist + update profile in one transaction), or defer non-critical logging to a background queue.

**FFmpeg Process Cleanup Not Guaranteed:**
- Issue: `discord.VoiceClient.play()` spawns FFmpeg via `discord.FFmpegOpusAudio()` or `discord.FFmpegPCMAudio()`. If the bot crashes before `voice_client.stop()` is called, or if an exception occurs between `.play()` and `.stop()`, FFmpeg processes remain orphaned.
- Files: `services/audio.py` (returns AudioSource objects), `cogs/music.py` (line 191 calls `voice_client.play()` with after-callback), `bot.py` (line 198 calls `vc.stop()` but only during idle timeout)
- Impact: Orphaned FFmpeg processes consume memory and file descriptors. On long-running bot, this accumulates until system OOM or file descriptor exhaustion.
- Fix approach: Explicitly track and kill FFmpeg processes before playback state changes. Wrap `voice_client.play()` in try/finally. Use `psutil` to monitor/kill orphans at startup.

**Bare `except Exception` Clauses with Silent `pass`:**
- Issue: `cogs/music.py` (lines 53, 222, 376, 620) and `services/audio.py` (line 63) catch all exceptions and either `pass` or ignore them. This silently swallows errors (e.g., invalid select menu index, missing metadata) without logging.
- Files: `cogs/music.py` (4 instances), `services/audio.py` (1 instance)
- Impact: Bugs are invisible. Users get no feedback when errors occur. Debugging impossible.
- Fix approach: Replace bare `except Exception:` with specific exception types. Always log before passing. Return an error embed to user when user-facing operations fail.

**yt-dlp No Auto-Update on Failure:**
- Issue: CLAUDE.md documents "daily auto-update at 4am" and "on download failure: attempt update → retry → fallback stream" but no background task implements this. If yt-dlp is broken, the bot doesn't self-heal.
- Files: `services/youtube.py` (no auto-update logic), `bot.py` (background tasks list incomplete)
- Impact: If YouTube changes API, yt-dlp breaks silently. Bot becomes unable to search/extract/download until manual redeploy.
- Fix approach: Add `@tasks.loop(time=datetime.time(4, 0))` to `bot.py` that runs `pip install -U yt-dlp`. Add auto-update to exception handler in `YouTubeService.download()`.

**Gemini Rate Limiter: Priority 2 Rejects But Logs Silently:**
- Issue: `services/gemini.py` (lines 73-76) rejects priority-2 requests (background tasks like auto-queue) if wait > 10s, but `cogs/ai.py` (line 179) catches and logs silently. No user sees "your auto-queue was rejected due to rate limit." Users may think their queue is empty when it's actually rate-limited.
- Files: `services/gemini.py` (lines 57-86), `cogs/ai.py` (lines 178-179)
- Impact: Auto-queue fails silently. Users perceive broken auto-queue.
- Fix approach: When priority-2 rejects, post a message to the text channel ("rate limit hit, skipping auto-queue") before silently exiting.

**First-Run Loads All Cogs Unconditionally:**
- Issue: `bot.py` (lines 250-251) loads `cogs.ai` and `cogs.imagine` during first-run even if `GEMINI_API_KEY` is not set. These cogs will fail to initialize because they reference `self.bot.gemini_service` which doesn't exist.
- Files: `bot.py` (first_run() function, lines 248-252)
- Impact: First-run sync command fails if Gemini key is missing. Initial slash command registration incomplete.
- Fix approach: In `first_run()`, check for Gemini key before loading AI/Imagine cogs (same logic as `on_ready()` lines 93-95).

**Playlist Error Path Doesn't Respond to User:**
- Issue: `cogs/music.py` (line 391-392) catches playlist extraction exceptions and logs them, but doesn't send an error message to the user. The defer() was called but no followup sent, leaving the user with "Thinking..." forever.
- Files: `cogs/music.py` (lines 341-393)
- Impact: User sees infinite loading spinner. No error feedback.
- Fix approach: Catch exceptions in playlist block and send error embed via `interaction.followup.send()`.

**Database Query Integer Coercion:**
- Issue: `database.py` (line 165) converts `limit` parameter to string: `LIMIT ?` with `str(limit)`. This works but is non-standard and confusing. If `limit` were somehow a dict/list, this would fail.
- Files: `database.py` (line 165)
- Impact: Minor — code works but looks wrong. Could lead to SQL injection if not careful in future changes.
- Fix approach: Pass `limit` directly as int, not `str(limit)`.

## Known Bugs

**Reconnect Attempt Race Condition:**
- Symptoms: Bot reconnects to voice channel, plays track, but playback freezes or skips unexpectedly.
- Files: `cogs/music.py` (lines 600-610)
- Trigger: Force disconnect bot from voice channel (e.g., move to different channel, or Discord connection drop + immediate bot crash)
- Root cause: On reconnect, `await before.channel.connect()` returns a new `voice_client` object, but the old `voice_client` reference in the cog may still be active. When `_play_track()` is called with the guild, it uses `guild.voice_client` which should be the new one, but the old one's after-callback may still fire. If timing is wrong, callbacks from old and new playback sessions interfere.
- Workaround: None — may require awaiting voice client stabilization or generation counter reset.

**Auto-Queue Suggestions JSON Parse Too Lenient:**
- Symptoms: Auto-queue adds no songs and silently exits.
- Files: `cogs/ai.py` (lines 185-200)
- Trigger: Gemini returns valid JSON but with extra markdown (e.g., ```json ... ``` with extra spaces/newlines). Regex cleanup (lines 188-189) misses edge cases.
- Root cause: Regex `^```(?:json)?\s*` and `\s*```$` don't account for all whitespace patterns Gemini might use.
- Workaround: Check logs for "Auto-queue JSON parse failed" and tune the regex.

**Idle Voice Channel Detection Only Counts Humans:**
- Symptoms: Bot stays connected indefinitely if other bots are in the channel.
- Files: `bot.py` (lines 189)
- Trigger: Another bot joins the voice channel. Idle check counts only humans, so if 1 bot + 0 humans, bot stays connected forever.
- Root cause: Intentional by design, but not documented. If intent is "leave when humans leave," then other bots shouldn't count.
- Workaround: Manual `/stop` command.

## Security Considerations

**.env File Not in Gitignore:**
- Risk: If developer commits `.env` with real tokens, secrets exposed in git history.
- Files: No actual `.env` in repo, but `.gitignore` should be checked.
- Current mitigation: `.env.example` exists; dotenv pattern is correct.
- Recommendations: Add explicit `*.env` and `.env.local` to `.gitignore`. Add pre-commit hook to prevent committing `.env*` files. Document that `.env` must never be committed.

**Gemini API Key Logged to File:**
- Risk: `services/gemini.py` (line 123) logs the full system prompt (which may contain user context) and `cogs/ai.py` (line 126) logs message contents to the logger. If API key is accidentally embedded in a system prompt or message, it gets written to `logs/dexter.log`.
- Files: `utils/logger.py`, `services/gemini.py` (line 123), `cogs/ai.py` (line 126)
- Current mitigation: API key is not logged directly, but sensitive user context might be.
- Recommendations: Sanitize system prompts before logging. Truncate sensitive message content to first 100 chars in logs.

## Performance Bottlenecks

**Audio Download Blocks Event Loop:**
- Problem: `YouTubeService.async_download()` (line 165-168) runs `download()` in an executor, which spawns yt-dlp as a subprocess. yt-dlp may take 5-10s for a video. During this time, the bot remains responsive (executor threads), but if the queue is high, multiple downloads compete for disk I/O.
- Files: `services/youtube.py` (lines 138-153), `cogs/music.py` (line 259)
- Cause: No queue or throttle on concurrent downloads. If 5 users `/play` simultaneously, 5 yt-dlp processes spawn at once.
- Improvement path: Implement a semaphore to limit concurrent downloads to 2-3. Queue excess downloads. Track download latency and warn user if > 5s.

**Cache Cleanup Linear Scan:**
- Problem: `services/audio.py` (line 69) lists all cache files and sorts by atime on every cleanup call (hourly). On a cache with 10K files, this is O(n log n) every hour.
- Files: `services/audio.py` (lines 67-88)
- Cause: No incremental cleanup or LRU tracking.
- Improvement path: Use `pathlib.Path.glob()` to filter only files older than N days before sorting. Or maintain a simple JSON index of file access times.

**Message Buffer Unbounded Growth Per Channel:**
- Problem: `models/message_buffer.py` (line 19) uses `deque(maxlen=10)` which is bounded, but if a bot is in 100+ channels, the `_buffers` dict grows unbounded. Each channel's deque is only 10 messages, but there's no eviction of unused channels.
- Files: `models/message_buffer.py`
- Cause: No TTL or cleanup for inactive channels.
- Improvement path: Add a timestamp to each channel's deque. Clear buffers for channels not seen in > 24 hours.

## Fragile Areas

**Auto-Queue Recommendation Parsing:**
- Files: `cogs/ai.py` (lines 113-122)
- Why fragile: Depends on Gemini returning valid JSON with exact `{"title": "...", "artist": "..."}` structure. If Gemini returns malformed JSON, the function silently fails (line 121 returns None), and auto-queue stops.
- Safe modification: Add a `default_suggestions` fallback. Log the raw response for debugging. Add timeout for Gemini response parsing.
- Test coverage: `tests/test_ai_helpers.py` likely has some tests, but edge cases (malformed JSON, missing fields) should be verified.

**Music Queue State Consistency:**
- Files: `models/queue.py`, `cogs/music.py` (queue manipulation: add, skip, advance, clear)
- Why fragile: `current_index` can become out of sync if tracks are removed/cleared while playback is happening. The `_play_generation` counter prevents double-play from stale callbacks, but doesn't protect against index out-of-bounds after a clear.
- Safe modification: When clearing or modifying the queue during playback, always check `0 <= current_index < len(tracks)` before accessing `get_current()`. Add guard assertions.
- Test coverage: `tests/test_queue.py` should cover edge cases like clear-during-playback.

**Voice Client State Tracking:**
- Files: `cogs/music.py` (voice_client.is_connected(), is_playing(), is_paused())
- Why fragile: Discord.py's `voice_client` state can become stale if Discord network events (disconnect/reconnect) happen rapidly. The bot's in-memory `queue.is_playing` flag may disagree with the actual FFmpeg process state.
- Safe modification: On reconnect, always reset `queue.is_playing = False` and `queue.is_paused = False`. Before calling `voice_client.play()`, verify `voice_client.is_connected()` and log if states differ.
- Test coverage: Hard to test without mocking Discord's websocket. Manual testing required for edge cases.

**Gemini Service Rate Limiter:**
- Files: `services/gemini.py` (lines 34-86)
- Why fragile: The sliding-window rate limiter uses `time.monotonic()` (good) but has a subtle bug: at line 83, after releasing the lock, another request could sneak in and exceed the limit momentarily. The `async with` pattern is correct, but the lock is released before the request is actually made.
- Safe modification: Ensure all rate-limited operations are called while holding the lock, or use a semaphore instead of a deque + lock.
- Test coverage: `tests/test_rate_limiter.py` should test concurrent requests at the limit boundary.

## Scaling Limits

**Single-Bot SQLite Bottleneck:**
- Current capacity: ~10 concurrent users, 100-200 songs/day
- Limit: When song logging + artist count + user profile updates exceed 3 concurrent writes, SQLite's default journal mode hits its 5s lock timeout and silently fails (or errors if not caught).
- Scaling path: Enable WAL mode, batch writes, or migrate to PostgreSQL (Phase 4 per CLAUDE.md).

**In-Memory Queue Storage:**
- Current capacity: ~500 tracks per guild before memory bloat (each Track ≈ 200 bytes)
- Limit: No per-guild queue size limit enforced. A user could `/play` 10K playlists sequentially and the queue would consume ~2MB per guild.
- Scaling path: Add `MAX_QUEUE_SIZE_PER_GUILD` config (e.g., 1000 tracks). Reject adds that exceed this.

**Gemini API 15 RPM Limit:**
- Current capacity: 15 requests/minute shared across `/ask`, `/imagine`, auto-queue, and any future AI features.
- Limit: If 10 users spam `/ask`, the first 5 succeed instantly, next 10 wait 60s, and background auto-queue is rejected.
- Scaling path: Implement per-guild rate limiting (5 RPM each) to isolate guilds. Or upgrade to paid Gemini tier with higher limits.

## Dependencies at Risk

**yt-dlp Brittle Dependency:**
- Risk: yt-dlp is unmaintained by YouTube and depends on reverse-engineering YouTube's API. YouTube changes break yt-dlp frequently (every few months).
- Impact: Download, search, and playlist extraction all fail silently or crash.
- Migration plan: Maintain a fallback search/download mechanism (e.g., YouTube Data API with fallback to Invidious/piped). Or monitor yt-dlp releases and auto-update daily.

**Discord.py Stability:**
- Risk: discord.py 2.x is actively maintained but has rare breaking changes between minor versions. Voice client APIs are especially brittle.
- Impact: Bot may fail to connect to voice, play audio, or handle disconnects.
- Migration plan: Pin discord.py version in requirements.txt. Test on new releases before upgrading.

**google-genai SDK Early/Unstable:**
- Risk: google-genai is Google's new Python SDK (released ~2024) and may have breaking changes or bugs.
- Impact: Gemini chat and image generation fail if SDK has bugs or API changes.
- Migration plan: Monitor google-genai releases. Fallback to REST API directly if SDK fails.

## Missing Critical Features

**No Queue Persistence:**
- Problem: If bot crashes, the queue is lost. Users lose all queued songs.
- Blocks: Multi-server reliability, high availability.
- Note: Phase 1 complete but persistence deferred to Phase 4 per CLAUDE.md.

**No Position Save on Disconnect:**
- Problem: If bot disconnects mid-song, playback resumes from the start of the track, not from where it stopped.
- Blocks: User experience (users want seamless reconnect).
- Note: CLAUDE.md mentions "Save position, reconnect, resume. 3 attempts then error" but not implemented.

**Phase 3 Events Not Implemented:**
- Problem: Unprompted roasts (voice join/leave), emoji reactions, repeat song detection, milestone roasts, streak tracking, idle loneliness messages, startup message, status rotation, and /lyrics are all documented in CLAUDE.md but not in code.
- Blocks: Core personality features. Bot is currently "alive" but not "alive enough."
- Note: Only `/ask` and `/imagine` partially implemented from Phase 2.

**No Designated Channel Config:**
- Problem: CLAUDE.md says "Designated channel only — don't spam every channel" but config has no `DESIGNATED_CHANNEL_ID`. AI responses go to whatever channel `/ask` was used in.
- Blocks: Multi-channel guilds can't centralize AI responses.
- Note: Config placeholder exists but not used.

## Test Coverage Gaps

**Music Playback Race Conditions:**
- What's not tested: Concurrent `/play` calls, skip during FFmpeg startup, reconnect + play timing.
- Files: `cogs/music.py` (playback engine), `models/queue.py` (state transitions)
- Risk: Subtle race conditions (double-play, stuck playback) go unnoticed until production.
- Priority: High — race conditions are production show-stoppers.

**yt-dlp Fallback Behavior:**
- What's not tested: Download timeout fallback, stream URL freshness, extraction retries on failure.
- Files: `services/audio.py` (line 58-65), `services/youtube.py` (lines 138-153)
- Risk: When download fails, stream fallback may use a stale URL that expires mid-playback.
- Priority: High — affects playback reliability.

**Gemini API Error Handling:**
- What's not tested: Network timeouts, 429 rate limit responses, malformed JSON responses, empty responses.
- Files: `services/gemini.py` (lines 99-161), `cogs/ai.py` (auto-queue parsing)
- Risk: Unhandled API errors crash cogs or result in silent failures.
- Priority: Medium — some errors are caught, but edge cases exist.

**Database Concurrent Writes:**
- What's not tested: 10+ simultaneous writes, database locked scenarios, transaction rollback.
- Files: `database.py`, `cogs/music.py` (lines 298-314 chain writes)
- Risk: Concurrent load exposes lost-write bugs.
- Priority: Medium — only matters under load, which hasn't been tested.

**Message Buffer Edge Cases:**
- What's not tested: Channel ID wrap-around, buffer pollution from deleted channels, timestamp accuracy over time.
- Files: `models/message_buffer.py`
- Risk: Minor — buffer is small and ephemeral. But should handle edge cases gracefully.
- Priority: Low.

---

*Concerns audit: 2026-06-01*
