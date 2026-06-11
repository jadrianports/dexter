---
phase: 03-alive
plan: "04"
subsystem: events/personality
tags: [voice-roasts, message-reactions, seasonal, gemini-ambient, events-cog]
dependency_graph:
  requires: [03-01]
  provides: [on_voice_state_update, _generate_ambient_roast, _get_ambient_channel, message-reactions, seasonal-expansion]
  affects: [cogs/events.py, personality/seasonal.py, tests/test_seasonal.py]
tech_stack:
  added: []
  patterns: [gemini-priority-2-background, ambient-cooldown-dict, d09-d10-channel-fallback, allowed-mentions-none]
key_files:
  created: []
  modified:
    - cogs/events.py
    - personality/seasonal.py
    - tests/test_seasonal.py
decisions:
  - "Maximize-AI decision (2026-06-11): join/leave/late-night roasts attempt priority-2 Gemini first, reusing get_user_summary taste path from /ask; fall back to template pool on GeminiRateLimitError or any exception"
  - "Channel-move complaint stays template-only (no per-user data to personalize); all other ambient posts go through _generate_ambient_roast"
  - "_generate_ambient_roast uses a focused standalone system prompt (under 200 chars target) instead of the full build_chat_prompt to keep token cost low for background calls"
metrics:
  duration: "~25 minutes"
  completed: "2026-06-11"
  tasks_completed: 2
  files_modified: 3
---

# Phase 03 Plan 04: Voice Roasts + Reactions + Seasonal Expansion Summary

**One-liner:** Gemini-first ambient voice roasts (priority-2, taste-personalized) with template fallback wired into on_voice_state_update; message reactions (eyes/salute/neutral/thanks-deflect) and four new seasonal branches with full test coverage.

## What Was Built

### Task 1 — on_voice_state_update + _generate_ambient_roast + Channel Resolver (cogs/events.py)

Extended the 33-line stub into a full ambient personality cog:

**`on_voice_state_update`:** Three branches in the correct order:
1. Bot-move complaint (checked before `if member.bot: return`) — always fires, template-only, `pick_random(roasts.BOT_MOVED_COMPLAINTS)`
2. `if member.bot: return` guard — drops all other bot voice events
3. JOIN path: rolls `config.UNPROMPTED_ROAST_CHANCE` (30%), checks ambient ceiling, branches on `is_late_night()` (50% second roll), calls `_generate_ambient_roast` with appropriate scenario + fallback pool
4. LEAVE path: same chance roll + ceiling check, calls `_generate_ambient_roast`
5. Channel-switch (both non-None, different) — explicitly ignored per D-12

**`_generate_ambient_roast(member, scenario, fallback_pool)`:** Maximize-AI implementation:
- Reuses `get_user_summary(db, str(member.id))` from `models.user_profile` — the exact same taste-summary function that `/ask` injects via `build_chat_prompt`. This gives Gemini the user's top artists, play counts, and most-repeated song.
- Calls `self.bot.gemini_service.chat(system_prompt, conversation, priority=2)` — same call pattern as `try_auto_queue` in `cogs/ai.py`. Priority=2 only, never priority=1.
- On `GeminiRateLimitError` or any other exception: falls back to `pick_random(fallback_pool)` with `{name}` formatting. Never raises.
- Enforces voice rules on Gemini output: strip to <=500 chars, lowercase first character.

**`_get_ambient_channel(guild)`:** D-09/D-10 four-step fallback chain:
1. `config.DEXTER_CHANNEL_ID` (explicit designation)
2. `music_cog.get_queue(guild.id)._text_channel_id` (last active music channel) — `getattr` with None default
3. `guild.system_channel` (permission-checked)
4. First writable text channel in `guild.text_channels`

**`_check_ambient_cooldown` / `_mark_ambient_roast`:** In-memory dict `{user_id: float}` tracking last roast time via `asyncio.get_event_loop().time()`. Unified ceiling — join + leave + late-night all share `config.AMBIENT_ROAST_CEILING_SECONDS` per D-13.

All `channel.send()` calls pass `allowed_mentions=discord.AllowedMentions.none()` preventing @everyone/@here injection from crafted `member.display_name` values (T-03-11 mitigation).

### Task 2 — Message Reactions + Seasonal Expansion

**`_handle_message_reactions(message)`:** Called from `on_message` after the buffer-feeding block (buffer feeding preserved intact):
- YouTube/Spotify URL in message content → `add_reaction("👀")`
- Message starts with/contains "goodnight" or "gn" (word-boundary regex) → `add_reaction("🫡")`
- Bot mentioned + thanks keywords ("thanks", "thank you", "ty", "thx", "thank u") → `channel.send("...you're welcome. don't get used to it.")` with `allowed_mentions=none`
- Bot mentioned + bare mention (no substance after stripping mention tags) → `add_reaction("😐")`
- All `add_reaction` calls wrapped in `try/except discord.HTTPException` — failed reactions degrade silently

**`personality/seasonal.py` expansion:** Four new branches added before `return ""`:
- `month == 11 and day >= 22` — Thanksgiving week (USA)
- `month == 3 and day == 17` — St. Patrick's Day
- `month == 7 and day == 4` — Fourth of July
- `month in (6, 7, 8)` — Generic summer (June–August)

Note: July 4 fires before the summer catch-all due to branch ordering.

**`tests/test_seasonal.py`:** Extended from 6 to 14 tests. New assertions cover Thanksgiving week (including boundary day 22), St. Patrick's Day, Fourth of July, summer June, summer August, non-seasonal September (empty), and non-seasonal early November (empty). All 14 pass.

## Commits

| Hash | Description |
|------|-------------|
| `494286f` | feat(03-04): voice join/leave/move roasts (Gemini-first) + ambient channel resolver |
| `6afe7a8` | feat(03-04): message reactions in on_message + expanded seasonal awareness |

## Maximize-AI Implementation Details

**Taste-summary helper reused:** `get_user_summary(db, user_id)` from `models/user_profile.py` — identical to what `cogs/ai.py::ask()` calls at line 101. Returns a natural-language string like "User 'marcus': 47 songs queued. Top artists: Drake (23), Morgan Wallen (12). Most repeated: Hotline Bling (7 times)."

**Gemini call signature:** `gemini_service.chat(system_prompt, conversation, priority=2)` — same signature as the auto-queue background call in `cogs/ai.py::try_auto_queue()` line 157.

**System prompt:** A lightweight standalone prompt (`_AMBIENT_ROAST_PROMPT`) rather than the full `build_chat_prompt` output — avoids injecting mood/seasonal context into a 1-line ambient call, keeping token cost low. Includes the same Dexter voice rules (lowercase, contempt outward, <=120 char target) and the user's taste summary.

**Fallback chain:** `GeminiRateLimitError` → template. Any other exception → template. Empty/None Gemini response → template. `gemini_service` attribute missing on bot → template. Never raises.

**Priority:** Always `priority=2`. Ambient roasts never contend with user `/ask` (priority=1) per the rate limiter contract in `services/gemini.py`.

## Tests / Verification

| Check | Result |
|-------|--------|
| `.venv/Scripts/python.exe -c "import cogs.events, personality.seasonal"` | PASS — clean import |
| `pytest tests/test_seasonal.py -x --tb=short` | PASS — 14/14 |
| `pytest -q` (full suite) | 251 passed, 1 known pre-existing failure (test_ytdlp_selfheal) |

## Must-Haves Status

| Truth | Met |
|-------|-----|
| Bot roasts users on voice join (30%) and leave (30%) within a unified per-user ambient ceiling, always complains when moved | Met |
| Bot delivers late-night (1-5am) roasts at 50% chance, sharing the ambient ceiling | Met |
| Join/leave/late-night roasts attempt priority-2 Gemini-personalized line first, fall back to template on rate-limit/failure | Met |
| Bot reacts to messages: eyes on YT/Spotify links, salute on goodnight/gn, neutral on bare mention, deflecting-warmth text on thanks | Met |
| Expanded seasonal awareness adds new date branches beyond the existing 5 | Met (4 new branches = 9 total) |

## Structural Review

| Check | Confirmed |
|-------|-----------|
| Bot-move branch fires before `if member.bot: return` | Yes — bot-move check is the first branch |
| `allowed_mentions=discord.AllowedMentions.none()` on all sends | Yes — bot-move, join, leave, thanks-deflect |
| Does not touch music idle timer | Yes — no reference to `_idle_seconds` or any idle-timer variable |
| `_generate_ambient_roast` never raises | Yes — all exception paths return fallback_line |
| Only `priority=2` used | Yes — single call site uses `priority=2` |
| `GeminiRateLimitError` caught | Yes — explicit except clause |
| `_get_ambient_channel` None-checks `queue._text_channel_id` | Yes — `getattr(queue, "_text_channel_id", None)` with None guard |

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Notes / Limitations

**Standalone ambient prompt vs. `build_chat_prompt`:** The plan specified using the "few-shot DEXTER voice (personality.prompts)" for Gemini calls. The implementation uses a focused standalone `_AMBIENT_ROAST_PROMPT` that encodes the same voice rules inline rather than calling `build_chat_prompt()`. Rationale: `build_chat_prompt` injects mood (requires a DB call), full seasonal context, and a 500-char response limit — all unnecessary overhead for a single ambient roast line. The standalone prompt is lighter, cheaper, and still produces the same Dexter register. The few-shot exemplars from `DEXTER_SYSTEM_PROMPT` informed the wording of `_AMBIENT_ROAST_PROMPT` but are not literally included to keep the prompt compact.

**`asyncio.get_event_loop().time()` deprecation note:** Python 3.12 may warn on `get_event_loop()` if no running loop exists. In practice this is always called from within the Discord event loop so it's safe. A future cleanup could use `asyncio.get_running_loop().time()` but that's out of scope for this plan.

## Known Stubs

None — all functionality is wired to real data sources (Gemini via `gemini_service`, taste data via `get_user_summary`/db).

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes beyond what the threat model in the plan already covers. T-03-11 (mention injection via display_name) mitigated by `allowed_mentions=none` on all sends.

## Self-Check

Files created/modified:
- `cogs/events.py` — exists, modified
- `personality/seasonal.py` — exists, modified
- `tests/test_seasonal.py` — exists, modified

Commits:
- `494286f` — confirmed in git log
- `6afe7a8` — confirmed in git log

## Self-Check: PASSED
