---
phase: 19-onboarding-admin-setup
reviewed: 2026-07-10T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - bot.py
  - cogs/admin.py
  - cogs/events.py
  - cogs/help.py
  - cogs/music.py
  - database.py
  - logic/guild_config.py
  - personality/roasts.py
  - services/guild_config.py
findings:
  critical: 1
  warning: 4
  info: 2
  total: 7
status: issues_found
---

# Phase 19: Code Review Report

**Reviewed:** 2026-07-10T00:00:00Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Reviewed the Phase 19 diff since `dacae17`: new `ambient_roasts_enabled`/`vision_roasts_enabled`
columns + DB helpers, the `AmbientSurface`-keyed pure/service resolution seam, `on_guild_join`/
`on_guild_remove` lifecycle glue + boot backfill, and the new `cogs/admin.py` `/setup` surface.
The surface-keyed pure logic (`logic/guild_config.py`) is clean and well-covered. The one BLOCKER
is a cache-consistency gap in `on_guild_join`'s "row already existed" branch: it never re-populates
the per-guild config cache that `on_guild_remove` evicted, so a kicked-and-re-invited guild goes
silently unconfigured for the rest of the bot's uptime, and a subsequent `/setup channel` run then
compounds the damage by resetting `vision_roasts_enabled` to `false` as if it were a genuine
first-time configure. Several lower-severity gaps (misleading boot-backfill summary reporting,
silent no-op admin writes, an incomplete permission pre-check) round out the warnings.

## Critical Issues

### CR-01: `on_guild_join` never refreshes the cache when the guild_config row already exists — silently un-configures a re-invited guild

**File:** `bot.py:669-676` (interacts with `bot.py:690-691` and `database.py:486-511`)

**Issue:**
`on_guild_remove` evicts the guild's entry from `GuildConfigService._cache`:

```python
# bot.py:690-691
if hasattr(bot, "guild_config"):
    bot.guild_config._cache.pop(str(guild.id), None)
```

`on_guild_join` only repopulates that cache entry on the "genuine new insert" branch:

```python
# bot.py:669-676
row = await database.insert_guild_config_if_absent(bot.pool, guild_id=str(guild.id))
if should_welcome_guild(inserted_row=row):
    bot.guild_config._refresh_cache_entry(row)
    welcome_posted = await _post_guild_welcome(guild)
else:
    # A row already existed for this guild_id — not a genuine new join
    # (e.g. a re-invite after a kick). Never welcome-spam (D-14).
    welcome_posted = False
```

`database.insert_guild_config_if_absent` (database.py:486) only returns a `Record` when the
`INSERT ... ON CONFLICT (guild_id) DO NOTHING` actually inserted a row; on conflict (the row
already exists — exactly the re-invite-after-kick case the comment names) it returns `None`, and
`should_welcome_guild` correctly evaluates to `False`. But the `else` branch does nothing to
recover the pre-existing row from the database, so the cache entry that `on_guild_remove` popped
is **never refreshed**. There is no other helper in `database.py` that fetches a single
`guild_config` row (only `load_all_guild_configs` and the two `*_if_absent` writers exist), so this
branch has no way to repair the cache even if it tried.

Concretely, for a guild that was previously `/setup`-configured (channel + toggles), then the bot
was kicked, then re-invited while the bot stays running (no restart in between):
1. `bot.guild_config.get(guild.id)` returns `None` for the rest of this process's uptime — every
   ambient surface (`resolve_ambient_channel`, `is_ambient_channel` for reactions/proactive/vision)
   treats the guild as *never configured*, even though the DB row and its settings are fully intact.
2. If an admin then runs `/setup channel` again (a reasonable thing to do since the bot appears
   unconfigured), `cogs/admin.py`'s `first_configure = cached is None or not cached["configured"]`
   evaluates `True` (cached is `None`), so it calls `configure_guild_first_time`, which — per its
   own documented contract (D-19/D-20) — unconditionally sets `vision_roasts_enabled = false`. This
   silently resets a toggle the guild owner had previously turned on, even though this is not
   actually a first-time configuration.

This is only masked at the *next full bot restart* because `GuildConfigService.load_all()` reloads
every row from the DB unconditionally at boot. Between a live kick+re-invite and the next restart,
the guild is fully but silently degraded.

**Fix:**
Add a real single-guild fetch and use it (or reuse) whenever the insert-if-absent call reports "row
already existed":

```python
# database.py — new helper
async def get_guild_config(pool: asyncpg.Pool, *, guild_id: str) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT " + _GUILD_CONFIG_RETURNING_COLUMNS + " FROM guild_config WHERE guild_id = $1",
            guild_id,
        )
```

```python
# bot.py::on_guild_join
row = await database.insert_guild_config_if_absent(bot.pool, guild_id=str(guild.id))
if should_welcome_guild(inserted_row=row):
    bot.guild_config._refresh_cache_entry(row)
    welcome_posted = await _post_guild_welcome(guild)
else:
    # Row already existed (e.g. re-invite after a kick) — on_guild_remove evicted
    # this guild's cache entry, so it MUST be re-fetched here or the guild reads
    # as unconfigured for the rest of this process's uptime.
    existing_row = await database.get_guild_config(bot.pool, guild_id=str(guild.id))
    if existing_row is not None:
        bot.guild_config._refresh_cache_entry(existing_row)
    welcome_posted = False
```

## Warnings

### WR-01: Boot-backfill summary embed labels guilds as "welcomed" even when the welcome send failed

**File:** `bot.py:450-472`

**Issue:** The boot backfill loop appends every genuinely-new guild to `_welcomed_this_boot`
regardless of whether `_post_guild_welcome` actually succeeded:

```python
bot.guild_config._refresh_cache_entry(_row)
_welcome_posted = await _post_guild_welcome(_guild)
log.info(... "welcome posted: %s", ... _welcome_posted)
_welcomed_this_boot.append((_guild.name, _guild.id))   # unconditional
```

`_post_guild_welcome` returns `False` on a missing resolvable channel or a send failure (both
non-fatal, per its own docstring), yet the resulting owner-facing embed always reads
`"Boot backfill: welcomed {N} guild(s)"` and lists every one of those guilds as if the welcome
message was actually delivered. Compare with the (correct) per-guild embed built by
`_build_guild_notice_embed`, which does carry a `welcome posted: yes/no` field for the live
`on_guild_join` path — the boot-backfill summary has no equivalent per-line status.

**Fix:** Track and report failures distinctly, e.g.:
```python
_welcomed_this_boot.append((_guild.name, _guild.id, _welcome_posted))
...
_summary_lines = "\n".join(
    f"{name} (`{gid}`) — welcome posted: {'yes' if posted else 'no'}"
    for name, gid, posted in _welcomed_this_boot
)
```

### WR-02: `/setup roasts` and `/setup vision` silently no-op (and still report success) when no guild_config row exists

**File:** `cogs/admin.py:176-177`, `cogs/admin.py:211-212`, `database.py:578-596`, `database.py:599-617`

**Issue:** `set_ambient_roasts_enabled`/`set_vision_roasts_enabled` are plain
`UPDATE ... WHERE guild_id = $1 RETURNING ...` statements — they return `None` (0 rows affected)
if no `guild_config` row exists yet for the guild. `GuildConfigService.set_ambient_roasts_enabled` /
`set_vision_roasts_enabled` only refresh the cache `if row is not None`, so a missing row means
the write is a complete no-op with no error raised anywhere. `AdminCog.setup_roasts` /
`setup_vision` don't check for this — they unconditionally reply `"roasts: on."` /
`"vision: on."` even though nothing was persisted:

```python
await self.bot.guild_config.set_ambient_roasts_enabled(guild_id=str(interaction.guild.id), enabled=enabled)
...
await interaction.response.send_message(f"roasts: {'on' if enabled else 'off'}.{gap_note}\n{echo}", ...)
```

In normal steady-state operation every current guild has a row (seeded at boot backfill or
`on_guild_join`), so this is a corner case — but it is reachable: the boot backfill loop
explicitly swallows per-guild insert failures (`except Exception: ... continue`, `bot.py:454-456`),
which on a transient Neon hiccup leaves exactly this "no row yet, but cogs already loaded and
`/setup` already available" state for that guild until the next restart.

**Fix:** Either upsert (mirroring `configure_guild_first_time`'s `INSERT ... ON CONFLICT DO UPDATE`
shape) so the toggle always persists regardless of row existence, or check the returned row and
tell the admin the write didn't take (e.g. `"couldn't save that — try /setup channel first."`)
instead of a blanket success message.

### WR-03: `/setup channel`'s pre-write permission check and the ambient-channel resolver only validate `send_messages`, never `view_channel`

**File:** `cogs/admin.py:123-130`, `services/guild_config.py:168-174`

**Issue:** Both the D-06 "loud refusal" pre-flight check in `setup_channel` and
`resolve_ambient_channel`'s post-configure guard check only `permissions_for(...).send_messages`:

```python
if not channel.permissions_for(interaction.guild.me).send_messages:
    ...
```

A channel overwrite that denies `view_channel` but happens to leave `send_messages` allowed (an
unusual but valid combination of Discord permission overwrites) passes this check, yet an actual
`channel.send()` will still fail with `Forbidden` in practice — defeating the documented intent of
D-06 ("the one deliberate loud-failure exception... refuses loudly, writing nothing, if it fails").

**Fix:** Also require `view_channel` in both checks:
```python
perms = channel.permissions_for(interaction.guild.me)
if not (perms.send_messages and perms.view_channel):
    ...
```

### WR-04: `on_guild_join` has no failure isolation around the DB write / welcome / notify chain

**File:** `bot.py:654-679`

**Issue:** Unlike the boot-backfill loop (which wraps its per-guild `insert_guild_config_if_absent`
call in `try/except Exception: ... continue` so one guild's DB hiccup doesn't derail the others),
`on_guild_join`'s call to `database.insert_guild_config_if_absent` is unguarded. A transient DB
error here propagates out of the listener (discord.py's default `on_error` logs and swallows it,
so the bot itself won't crash), but the owner never gets the join notification embed, and there is
no retry until the next full restart's boot backfill pass silently recovers it. This is
inconsistent with the resilience discipline the rest of this phase's DB call sites follow
(boot backfill, `taste_distill_batch`, `memory_distill_batch` all wrap their per-item DB round-trip
in `try/except: continue`).

**Fix:** Wrap the `insert_guild_config_if_absent` call (and ideally the whole handler body) in a
`try/except Exception` that still attempts `bot.log_to_discord`'s join notice on failure (with
`welcome_posted=False`), matching the resilience pattern used elsewhere in this file.

## Info

### IN-01: `services/guild_config.py` module docstring is stale about `resolve_announce_channel`'s callers

**File:** `services/guild_config.py:17-19`

**Issue:** The class-level docstring still reads *"It has ZERO callers this phase — Phase 19's
join-welcome flow is the intended first caller."* This text was accurate under Phase 18 but this
very diff (Phase 19) adds the first real caller (`bot.py::_post_guild_welcome`). The comment is
now misleading to a future reader trying to find all call sites.

**Fix:** Update the docstring to state that `bot.py::_post_guild_welcome` is now the (sole) caller.

### IN-02: `_refresh_cache_entry`'s docstring doesn't list `on_guild_join` / boot-backfill as callers

**File:** `services/guild_config.py:97-103`

**Issue:** The docstring says *"Only `seed_home_guild` calls this in Phase 18; Phase 19's `/setup`
and Phase 20's kill-switch call it after their own writes"* — but this phase's `bot.py` also calls
`_refresh_cache_entry` directly from `on_guild_join` and the boot backfill loop. Not incorrect
(the codebase has an established convention of cooperating modules touching underscore-prefixed
internal seams, e.g. `queue._play_generation`, `vc._idle_seconds`), but the docstring's caller
inventory is now incomplete and should be updated so the next reader isn't misled about the seam's
actual usage surface — especially relevant given the CR-01 finding above turns on exactly this
caller set.

**Fix:** Add `bot.py::on_guild_join` and the boot backfill loop to the documented caller list.

---

_Reviewed: 2026-07-10T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
