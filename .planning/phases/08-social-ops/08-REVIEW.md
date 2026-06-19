---
phase: 08-social-ops
reviewed: 2026-06-19T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - bot.py
  - cogs/ai.py
  - cogs/ops.py
  - config.py
  - database.py
  - personality/responses.py
  - personality/roasts.py
  - services/gemini.py
  - tests/test_database_phase8.py
  - tests/test_health_endpoint.py
  - tests/test_rate_limiter.py
  - tests/test_roast_command.py
  - utils/embeds.py
  - utils/logger.py
findings:
  critical: 0
  warning: 6
  info: 5
  total: 11
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-06-19
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Phase 8 adds the `/roast @user` command, the `/leaderboard` + `/stats` OpsCog, a degraded-but-200 `/health` endpoint, Postgres leaderboard/stats helpers, Gemini RPM getters, and a `total_errors` error-log increment.

The security posture is solid: all SQL uses `$N` positional parameters (no interpolation except the `increment_daily_stat` field name, which is allowlist-gated), the `/stats` owner gate fires before any data access, `/leaderboard` defers publicly while `/stats` defers ephemerally, `/roast` uses `AllowedMentions.none()`, and `/health` always returns HTTP 200. No BLOCKER-class defects were found.

However, several correctness and robustness defects degrade the feature: the leaderboard counts auto-queued songs (which are attributed to the bot's own user id), the `total_errors` counter over-counts because it increments on every embed sent to the error channel, the `/roast` daily-stat increments run even when the interaction failed, and three test files contain fragile or under-asserting patterns. None block shipping but all should be fixed.

## Warnings

### WR-01: `/leaderboard` "most songs queued" counts AI auto-queued songs and can rank the bot itself

**File:** `database.py:380-401` (`get_leaderboard_songs`)
**Issue:** The query counts every `song_history` row per `user_id` with no `was_auto_queued = false` filter. Auto-queued tracks are written with `requested_by=self.bot.user.id` (`cogs/ai.py:287-288`), and `log_track_batch` records that user_id into `song_history`. Because the query does `JOIN user_profiles up USING (user_id)`, the bot will appear on the public leaderboard the moment a `user_profiles` row exists for the bot id — and even when it does not, every auto-queued song inflates the human-attributed total wherever the auto-queue path attributes a real user. The leaderboard claims to rank human queuing behavior but silently includes machine-generated queue activity, which is a correctness/fairness defect for a public, competitive surface.
**Fix:** Exclude auto-queued rows from the human leaderboard:
```python
" FROM song_history sh"
" JOIN user_profiles up USING (user_id)"
" WHERE sh.guild_id = $1 AND sh.was_auto_queued = false"
" GROUP BY sh.user_id, up.username, up.first_seen_at"
```
If the intent is to also keep the bot off the board explicitly, add `AND sh.user_id <> $3` and pass `str(bot.user.id)`.

### WR-02: `total_errors` increments on every embed sent to the error channel, not only on errors

**File:** `utils/logger.py:62-73`
**Issue:** `log_to_discord` is the generic error-channel sender. It increments `total_errors` after *any* successful `channel.send(embed=...)`. The global handler at `bot.py:434-441` routes unhandled-command embeds through it, but `log_to_discord` is also the channel for daily summary embeds and any future informational embed. The counter is therefore "embeds posted to the error channel," not "errors," so the `/stats` "errors logged" field is misleading and will over-count whenever a non-error embed is sent through this path.
**Fix:** Increment from the actual error sites (or add an `is_error: bool = True` parameter to `log_to_discord` and only increment when true), rather than unconditionally on every embed send:
```python
async def log_to_discord(bot, embed, *, count_as_error: bool = True) -> None:
    ...
    await channel.send(embed=embed)
    if count_as_error and (pool := getattr(bot, "pool", None)) is not None:
        ...
```
Daily-summary / informational callers pass `count_as_error=False`.

### WR-03: `/roast` increments daily stats even when the interaction failed or was rate-limited

**File:** `cogs/ai.py:213-215`
**Issue:** The two `increment_daily_stat` calls run unconditionally after the try/except block. If the Gemini call raised `GeminiAPIError`/`GeminiRateLimitError` (handled) the command still counts as a successful `total_ai_queries`. Worse, the increments are reached even though earlier `followup.send` calls could have failed inside the handled branches — the stat write fires regardless of whether the user received output. This skews the `/stats` dashboard the command itself feeds.
**Fix:** Only count `total_ai_queries` on a successful Gemini response, and guard against the followup having failed. At minimum, move `total_ai_queries` into the success path:
```python
result = await self.gemini.chat(...)
if result:
    ...
    await increment_daily_stat(self.bot.pool, "total_ai_queries")
# total_commands can stay unconditional (matches /ask), but ai_queries should track real calls
```

### WR-04: `gather_bot_metrics` swallows all queue-count exceptions with a bare `pass`, masking real failures

**File:** `cogs/ops.py:90-97`
**Issue:** The per-guild queue loop wraps `music_cog.get_queue(guild.id)` in `try/except Exception: pass`. The stated intent ("one guild failure must not abort the rest") is reasonable, but a blanket silent swallow hides programming errors (e.g. a renamed attribute, a `None` queue) and will silently report `queue_count = 0` forever if `get_queue`'s contract changes. Since this same helper backs the `/health` degraded check, a systematic failure here would never surface.
**Fix:** Narrow the catch and log at debug/warning so the failure is observable:
```python
except Exception as exc:
    log.debug("queue_count probe failed for guild %s: %s", guild.id, exc)
    continue
```

### WR-05: `test_health_endpoint` re-implements the handler body logic instead of exercising it

**File:** `tests/test_health_endpoint.py:87-94, 110-122, 142-157`
**Issue:** All three tests copy the body-selection branch (`if reasons: json.dumps(...) else '{"status":"ok"}'`) inline rather than invoking the actual `health` handler in `bot.py`. The test comment even acknowledges this. This means the assertion "HTTP status is always 200" (the central D-28 guarantee) is never actually checked against the real handler — `test_health_always_200` only verifies that `gather_bot_metrics` returns a dict and that a re-implemented branch produces valid JSON. A regression in `bot.py`'s `health()` (e.g. someone setting `status=503` on degraded) would pass all three tests.
**Fix:** Import and call the real handler with a fake `aiohttp` request, and assert on `Response.status == 200` and `Response.text`. If the closure-over-`bot` structure makes that hard, refactor the body-selection into a small pure function in `bot.py` (e.g. `_health_body(reasons)`) and import *that* into the test so both the test and the handler share one implementation.

### WR-06: `test_health_endpoint._make_fake_bot` mutates `type(bot).__contains__`, leaking across tests

**File:** `tests/test_health_endpoint.py:62-64`
**Issue:** `type(bot).__contains__ = MagicMock(return_value=False)` patches the class of the MagicMock, not the instance. Because every `MagicMock()` shares the same dynamically generated type family, this mutation can leak into other mocks created in the same test session and is never torn down. The accompanying lines (`bot._spec_class = None`, the `hasattr`/`del` dance) are confused attempts to force `hasattr(bot, "_start_monotonic") == False` — on a plain `MagicMock`, `hasattr` is always `True` for any attribute, so `gather_bot_metrics` will actually take the uptime branch and read a `MagicMock` for `_start_monotonic`, then compute `time.monotonic() - <MagicMock>`, which would raise a `TypeError` inside `gather_bot_metrics`. The test only passes because that line is reached after the dict is built... it is not — it would raise. This is a latent flaky/incorrect test setup.
**Fix:** Use a real lightweight object or a `MagicMock(spec=...)` with explicit attributes, and explicitly delete `_start_monotonic`:
```python
bot = MagicMock(spec=["guilds", "voice_clients", "is_ready", "shard_count", "cogs", "pool"])
# spec restricts attributes, so hasattr(bot, "_start_monotonic") is False
```
Do not patch `type(bot).__contains__`. Verify the test actually exercises the no-uptime branch.

## Info

### IN-01: `increment_daily_stat` interpolates the field name into SQL (allowlist-gated, low risk)

**File:** `database.py:284-291`
**Issue:** The `{field}` f-string interpolation into the SQL text is safe only because of the `allowed_fields` set check above it. This is correct today, but it is the one place in the changed code that builds SQL by string formatting; a future edit that adds a field to the allowlist without auditing the call sites could reintroduce risk.
**Fix:** No change required; consider a comment reaffirming the invariant, or map field→fixed-SQL-statement to remove interpolation entirely.

### IN-02: `get_images_today_global` uses `generated_at::date = CURRENT_DATE` (UTC), diverging from the app's `date.today()` window

**File:** `database.py:466-471` and `database.py:362` (`get_daily_stats_row` uses `date.today().isoformat()`)
**Issue:** `/stats` mixes two "today" definitions: `get_daily_stats_row` keys on the host-local `date.today()`, while `get_images_today_global` uses Postgres `CURRENT_DATE` (server tz, typically UTC). On a UTC host these agree, but per CLAUDE.md the project is explicit that community-time checks must use `ZoneInfo(STREAK_TIMEZONE)` and that naive host time fires on the wrong calendar day. The two stat fields can disagree near midnight.
**Fix:** Make both windows use the same timezone basis — either compute the date in `STREAK_TIMEZONE` and pass it as a `$1` param, or cast with an explicit `AT TIME ZONE`.

### IN-03: `/roast` `>500` truncation contradicts the prompt's "under 200 characters" instruction

**File:** `cogs/ai.py:194-197`
**Issue:** The Gemini prompt asks for "under 200 characters," but the enforcement truncates only at 500. A 350-char model response (violating the prompt) passes through untouched. Minor, but the guardrail does not match the stated contract.
**Fix:** Truncate at 200 to match the prompt, or relax the prompt to 500 to match the guard — pick one source of truth.

### IN-04: `gather_bot_metrics` returns `degraded_reasons` for "gateway not ready" but `/health` may run before `_start_monotonic` is set

**File:** `cogs/ops.py:118-127`, `bot.py:390-392`
**Issue:** `bot._start_monotonic` is set at the very end of `_initialize_once`. The `/health` handler can fire earlier (Pitfall 6 is acknowledged). During that window `uptime_seconds` reports `0.0` while the DB probe may already succeed, so `/health` could report `ok` with zero uptime — cosmetically odd but harmless. Worth a comment so it is not mistaken for a stuck clock.
**Fix:** None required; optionally treat unset `_start_monotonic` as a transient "starting up" reason if you want `/health` to reflect cold start.

### IN-05: `test_roast_command._invoke_roast` does not exercise the cooldown decorator, so the cooldown is untested

**File:** `tests/test_roast_command.py:77-87`
**Issue:** The tests call `cog.roast.callback(...)`, deliberately bypassing the `@app_commands.checks.cooldown` decorator. That is fine for testing the body, but it means the Phase-8 cooldown change (`ROAST_COOLDOWN_SECONDS` 300→30 in `config.py:64`) has zero test coverage, and there is no assertion that cooldown rejection is handled by the global `on_app_command_error`. Given the cooldown value was deliberately changed this phase, the lack of any cooldown assertion is a gap.
**Fix:** Add a test that constructs the `app_commands.Command` and verifies the cooldown is registered (1 use / `config.ROAST_COOLDOWN_SECONDS`), or document that cooldown behavior is covered by the shared global handler test elsewhere.

---

_Reviewed: 2026-06-19_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
