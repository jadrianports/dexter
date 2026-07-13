---
phase: 20-owner-control-plane-rate-observability
reviewed: 2026-07-13T16:50:45Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - bot.py
  - cogs/ai.py
  - cogs/events.py
  - cogs/imagine.py
  - cogs/library.py
  - cogs/music.py
  - cogs/ops.py
  - config.py
  - database.py
  - logic/guild_config.py
  - services/gemini.py
  - services/guild_config.py
  - services/memory.py
  - tests/conftest.py
  - tests/test_database_phase20.py
  - tests/test_gemini.py
  - tests/test_guild_config_logic.py
  - tests/test_guild_config_service.py
  - tests/test_guilds_group.py
  - tests/test_proactive_events.py
  - tests/test_vision_events.py
findings:
  critical: 0
  warning: 2
  info: 4
  total: 6
status: issues_found
---

# Phase 20: Code Review Report

**Reviewed:** 2026-07-13T16:50:45Z
**Depth:** standard
**Files Reviewed:** 20
**Status:** issues_found

## Summary

Reviewed the Phase 20 "Owner Control Plane & Rate Observability" change set: the
`DexterCommandTree.interaction_check` choke point (bot.py), the `/guilds` owner
command group (cogs/ops.py), the `guild_blocklist` table + `set_silenced`
helpers (database.py), the blocklist/silence extensions to `GuildConfigService`
(services/guild_config.py), the `decide_interaction_allowed` pure predicate
(logic/guild_config.py), the per-guild AI usage counter (services/gemini.py),
and the `guild_id` threading + mid-flight silence re-checks across the cogs.

Overall the enforcement design is sound and defended by strong tests. The
adversarial focus areas held up under trace:

- **Owner-gate bypass:** none found. The choke point owner-bypasses first
  (`decide_interaction_allowed` returns `True` for `is_owner`), and every
  `/guilds` subcommand independently re-gates with an inline
  `await self.bot.is_owner(...)` as its first statement. A non-owner cannot
  reach any owner action through either surface.
- **Silence enforcement:** verified end-to-end. `silenced` is present in
  `_GUILD_CONFIG_RETURNING_COLUMNS` and in `load_all_guild_configs`' SELECT, so
  the cache push after `silence_guild` actually carries the flag — the O(1)
  `is_silenced` read is truthful. `/setup` writes never reset `silenced`, and
  even if they did, a silenced guild's admins are locked out of `/setup` by the
  same choke point, closing the self-unsilence escape.
- **Blocklist persistence:** the dedicated `guild_blocklist` table is proven by
  `test_blocklist_independent_of_guild_config` to survive a `guild_config`
  delete (the Phase 21 purge), and `on_guild_join` re-leaves a blocklisted
  re-invite before any insert/welcome.
- **`guild_id` threading:** consistent — every call site passes `str(...)`,
  every store/read coerces via `str()`, DM/background calls pass `None` and are
  correctly excluded (D-09).
- **TOCTOU:** the proactive daily-cap reserve-before-await + release-on-non-fire
  and the pre-send silence re-checks (proactive + vision) are correct and
  release/skip on every bail path.

Two WARNING-level defects and four INFO items are detailed below. The most
material is a latent correctness gap in the async choke point for autocomplete
interactions.

## Warnings

### WR-01: `interaction_check` mishandles autocomplete interactions — sends an invalid response type

**File:** `bot.py:88-120` (`DexterCommandTree.interaction_check`)
**Issue:**
The docstring claims the mechanic was "verified against installed discord.py
2.7.1," but the verification missed that `CommandTree._call` runs
`interaction_check` **unconditionally at the very top, before the autocomplete
branch**. Confirmed in the installed source
(`discord/app_commands/tree.py:1258-1300`): line 1259 awaits
`interaction_check`, and the `InteractionType.autocomplete` handling is not
reached until line 1283.

Consequently, for a **non-owner in a silenced or blocked guild**, an
*autocomplete* interaction enters `interaction_check`, `decide_interaction_allowed`
returns `False`, and the code executes:

```python
if not interaction.response.is_done():
    await interaction.response.send_message("i've been muted in this server. ...", ephemeral=True)
```

`send_message` emits `InteractionResponseType.channel_message_with_source`
(type 4), which Discord rejects with a 400 for an autocomplete interaction. The
`HTTPException` propagates out of `interaction_check` (line 1259 is not wrapped
in a try/except), producing an error-log spew and a broken autocomplete instead
of the intended silent refusal.

This is currently **latent** — the codebase registers only static `choices=`
(client-side, no autocomplete interaction), so no `@app_commands.autocomplete`
handler exists today. But it is a live trap: the first autocomplete command
added to any cog will break for every non-owner in a silenced guild.

**Fix:** guard the refusal on the interaction type — only refuse (and only send)
for real application-command invocations; for autocomplete, silently return
`False` without sending:

```python
if not allowed:
    if (
        interaction.type is discord.InteractionType.application_command
        and not interaction.response.is_done()
    ):
        await interaction.response.send_message(
            "i've been muted in this server. not my call.",
            ephemeral=True,
        )
    return False
```

### WR-02: Refusal copy conflates "blocked" and "silenced," and blocked guilds should never reach it

**File:** `bot.py:110-116`
**Issue:**
The single refusal string `"i've been muted in this server. not my call."` is
sent for both the `blocked` and `silenced` branches. A `blocked` guild is
supposed to be force-left already (D-11 block-implies-leave), so the only way a
user reaches this line while `blocked` is the acknowledged
block-written-while-leave-in-flight window (T-20-03) — during which "i've been
muted" is misleading (the bot is actually mid-departure, not muted). More
importantly, there is no distinct signal/log emitted when the *blocked* branch
fires, so an operator cannot tell from behavior whether a refusal came from a
silence (expected, recoverable) or a stale-block race (should self-heal on the
next `on_guild_join`/reconnect).

This is a robustness/observability gap rather than an incorrect-authorization
bug — the decision (`False`) is correct in both cases.

**Fix:** branch the copy (or at least log the blocked case) so the two states
are distinguishable, e.g.:

```python
if not allowed:
    if interaction.type is discord.InteractionType.application_command and not interaction.response.is_done():
        msg = "i'm not welcome here anymore." if blocked else "i've been muted in this server. not my call."
        await interaction.response.send_message(msg, ephemeral=True)
    if blocked:
        log.info("interaction_check: refused command in blocked guild %s (leave likely in flight)", guild_id)
    return False
```

## Info

### IN-01: Per-guild usage counter increments before the API call, counting failures as "usage"

**File:** `services/gemini.py:224-226` (chat) and `304-306` (generate_image)
**Issue:** The `_guild_usage` increment happens immediately after
`_rate_limiter.acquire(priority)` and *before* the `generate_content` call, so a
request that then raises `GeminiAPIError`/`GeminiRateLimitError` or returns a
safety-blocked/empty response is still counted. For a "budget hog" triage view
(`/guilds list` sorted by usage) this is arguably acceptable (it counts
rate-limiter admissions), but the counter is labelled "calls this session" and
will over-report against actual successful completions. Worth a one-line doc
note, or move the increment to the success path if the intent is "successful
calls."
**Fix:** either document "counts dispatched attempts, not successes" on
`guild_usage`, or increment only after a non-exception return.

### IN-02: `_guild_usage` never evicts departed/blocked guilds

**File:** `services/gemini.py:163`, `on_guild_remove` (bot.py:761-773)
**Issue:** `on_guild_remove` evicts the `guild_config` cache entry but nothing
prunes `GeminiService._guild_usage`. Entries for left/blocked guilds linger for
the process lifetime. Bounded by the number of distinct guilds seen per session
(not a leak of concern at this scale), but the stale entries can still surface
in `/guilds list` sorting math if a guild is re-examined. Cosmetic.
**Fix:** optionally `self.gemini_service._guild_usage.pop(str(guild.id), None)`
in `on_guild_remove`, guarded by `getattr`.

### IN-03: `/guilds list` renders `member_count` unguarded (`None members`)

**File:** `cogs/ops.py:434-437`
**Issue:** `g.member_count` can be `None` for a not-yet-chunked/uncached guild,
producing the literal `"None members"` in a row. Not a crash, just untidy owner
output.
**Fix:** `f"{g.member_count or '?'} members"`.

### IN-04: Choke-point boot-race is wider than the docstring states

**File:** `bot.py:91-96`
**Issue:** The docstring frames the fail-open case as "the service itself is
structurally absent" (`guild_config is None`). But there is a second, undocumented
window: `guild_config` is *attached* yet `load_all()` has not finished, so
`_blocked` is an empty set and `_cache` is empty — every guild reads as
not-blocked / not-silenced and is allowed. A blocklisted guild's interaction
arriving in that window would not be refused. In practice a blocked guild has
already been left, and the window is milliseconds at boot, so impact is minimal;
flagging for accuracy so the "service absent -> fail open" comment is not
mistaken for full coverage.
**Fix:** no code change required; note the load-not-complete window in the
comment, or gate on a "blocklist loaded" flag if stricter behavior is ever
wanted.

---

_Reviewed: 2026-07-13T16:50:45Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
