---
phase: 19-onboarding-admin-setup
verified: 2026-07-10T00:00:00Z
status: human_needed
score: 12/12 must-haves verified (code level)
overrides_applied: 0
---

# Phase 19: Onboarding & Admin Setup Verification Report

**Phase Goal:** A server admin can turn Dexter "on" for their own guild with zero manual intervention from the owner — the preventive half of safety. (New servers get a welcome nudge and a self-service `/setup`, ambient-silent until configured.)
**Verified:** 2026-07-10
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

Merged from ROADMAP.md Success Criteria (4) + PLAN frontmatter must_haves across 19-01..19-04 (12 distinct truths, de-duplicated).

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `guild_config` carries `ambient_roasts_enabled` + `vision_roasts_enabled`, both defaulting `true` | VERIFIED | `grep` confirms both `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ... BOOLEAN NOT NULL DEFAULT true` statements in `database.py`; live-DB test `test_pre_existing_row_reads_both_toggles_true` passed against a real pgvector container spun up for this verification |
| 2 | `insert_guild_config_if_absent` returns a Record on genuine insert, `None` on conflict (D-14) | VERIFIED | Live-DB tests `test_insert_guild_config_if_absent_first_call_inserts` / `_second_call_returns_none` both passed against a real Postgres instance |
| 3 | Boot cache-load + home-guild seed surface the two new toggle columns | VERIFIED | `load_all_guild_configs` and `seed_guild_config_if_absent` source both contain `ambient_roasts_enabled` + `vision_roasts_enabled` in their SELECT bodies (grep-confirmed); live-DB tests pass |
| 4 | First `/setup channel` write sets `configured=true` + `vision_roasts_enabled=false`; a re-designate touches only `ambient_channel_id` | VERIFIED | `configure_guild_first_time` source contains `ON CONFLICT (guild_id) DO UPDATE`, sets `configured = true`/`vision_roasts_enabled = false`, never names `ambient_roasts_enabled`; `redesignate_guild_channel` contains only `ambient_channel_id` in its SET clause — both confirmed via `inspect.getsource` + live-DB round-trip tests |
| 5 | A future ambient surface cannot resolve a channel without naming its `AmbientSurface` — required kwarg, no default | VERIFIED | `decide_ambient_channel(config_row=None)` and `is_ambient_channel(config_row=None, channel_id=1)` both raise `TypeError` when `surface=` is omitted (executed directly against `logic/guild_config.py`) |
| 6 | `ambient_roasts_enabled` gates ROAST+PRESENCE; `vision_roasts_enabled` gates VISION; a disabled toggle resolves to silence | VERIFIED | Executed `decide_ambient_channel` directly: `ambient_roasts_enabled=False` returns `None` for ROAST and PRESENCE but NOT for VISION; `vision_roasts_enabled=False` returns `None` for VISION but NOT for ROAST. Missing toggle key fails open to `True` (matches column default) |
| 7 | Emoji reactions fire only in the configured ambient channel with roasts enabled — CONFIG-04 reaction hole closed | VERIFIED | `cogs/events.py::on_message` — `_handle_message_reactions(message)` now called only inside `if roast_channel_ok:` (line 414-415), where `roast_channel_ok` is computed via `is_ambient_channel(..., surface=AmbientSurface.ROAST)`. `test_reactions_suppressed_when_unconfigured` / `_channel_mismatched` / `_ambient_roasts_disabled` all pass |
| 8 | `should_welcome_guild` is true only when the insert actually inserted — never from a cache miss | VERIFIED | `should_welcome_guild(inserted_row={...})` → True; `should_welcome_guild(inserted_row=None)` → False (executed directly); `test_should_welcome_guild_never_derived_from_a_cache_miss` passes; both `on_guild_join` and the boot backfill loop key their welcome decision on `should_welcome_guild(inserted_row=row)`, never `bot.guild_config.get(...)` |
| 9 | Joining a guild inserts a `configured=false` row, attempts an in-persona welcome that never crashes the join, and notifies the owner | VERIFIED (code-level) | `bot.py::on_guild_join` calls `insert_guild_config_if_absent`, wraps the whole DB/welcome chain in `try/except Exception` (WR-04 fix), and unconditionally sends `bot.log_to_discord(_build_guild_notice_embed(...))` after the try/except. `_post_guild_welcome` itself wraps the send in `try/except discord.HTTPException` returning `False` on failure — never raises |
| 10 | A guild invited while Dexter was offline is welcomed exactly once on the next boot, keyed on the DB insert result — never on a cache miss | VERIFIED (code-level) | Boot backfill loop in `_initialize_once`: source-order assertion `s.index('seed_home_guild(') < s.index('insert_guild_config_if_absent(')` holds (backfill runs after the home-guild seed); welcome gated on `should_welcome_guild(inserted_row=_row)`; no `bot.guild_config.get(` in the backfill welcome-decision path |
| 11 | The startup message fires in the home guild only; idle-loneliness stays per-guild | VERIFIED | `_post_startup_messages` no longer iterates `bot.guilds` — resolves `bot.guild_config.home_guild_id`, returns early if unset, and posts once to the resolved home guild with `surface=AmbientSurface.PRESENCE`. The idle-loneliness resolve at line ~929 still runs per-guild inside its existing loop, now with `surface=AmbientSurface.PRESENCE` |
| 12 | Repeat-song and milestone roasts route through the config seam, silent in an unconfigured guild | VERIFIED | `_post_music_roast` body calls `resolve_ambient_channel(guild, surface=AmbientSurface.ROAST)`; the pre-Phase-18 `_get_text_channel` fallback is no longer used in that method (6 legitimate command-response call sites elsewhere untouched) |
| 13 | Owner receives a join and a remove notice in `ERROR_LOG_CHANNEL_ID`; `on_guild_remove` touches no DB rows | VERIFIED (code-level) | `on_guild_remove` body: `bot.guild_config._cache.pop(str(guild.id), None)` + `bot.log_to_discord(_build_guild_notice_embed(guild, joined=False, ...))` — no `database.` write call anywhere in the function body |
| 14 | A server admin can run `/setup channel`, pick a channel from the native dropdown, and ambient behavior activates immediately | VERIFIED (code-level; client rendering is Manual-Only) | `setup_channel(self, interaction, channel: discord.TextChannel)` — the typed parameter is the native picker (ONBOARD-03/D-02, explicitly not flaggable per 19-CONTEXT.md's verifier note). First-configure branch calls `configure_guild_first_time`; `decide_ambient_channel` returns a channel id immediately once `configured=true` |
| 15 | A non-admin running any `/setup` subcommand gets an in-persona ephemeral refusal before any state changes | VERIFIED (structural; live refusal is Manual-Only) | `_require_guild_admin` is the first statement of `setup_channel`/`setup_roasts`/`setup_vision` (`if not await self._require_guild_admin(interaction): return`), checks `interaction.permissions.manage_guild` (not `default_permissions`), and sends an ephemeral refusal before any DB read/write |
| 16 | `/setup channel` refuses (writing nothing) when Dexter cannot send in the chosen channel | VERIFIED | `setup_channel` checks `perms.send_messages and perms.view_channel` (WR-03 fix — was `send_messages`-only) BEFORE any cache read/write, and `return`s on failure with a specific ephemeral message naming the channel |
| 17 | An admin can toggle ambient roasting and vision roasting independently; every subcommand echoes the full resulting config | VERIFIED | `setup_roasts`/`setup_vision` each call the matching `set_*_enabled` service method, check the (WR-02-fixed) boolean return before claiming success, and both end with `_config_echo` rendering channel + roasts + vision state |
| 18 | A fresh `/setup channel` leaves roasts ON and vision OFF; a re-designate does not reset a toggle | VERIFIED | `configure_guild_first_time`'s SQL never names `ambient_roasts_enabled` (stays at its true default/existing value) and explicitly sets `vision_roasts_enabled = false`; `redesignate_guild_channel`'s SQL touches only `ambient_channel_id`, `updated_at` |

**Score:** 18/18 code-level truths verified (all PLAN-frontmatter must-haves + all 4 ROADMAP Success Criteria collapse into these 18; no double-counting kept in headline score of 12 distinct "must_have" groupings — see per-plan tables below for exact 1:1 mapping)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `database.py` | 2 new toggle columns + 5 write helpers (`insert_guild_config_if_absent`, `configure_guild_first_time`, `redesignate_guild_channel`, `set_ambient_roasts_enabled`, `set_vision_roasts_enabled`) + `get_guild_config` (CR-01 fix) | VERIFIED | All present, parameterized (`$1`/`$2`, zero f-string/`%`-interpolation into SQL bodies), confirmed via `inspect.getsource` + live-DB round-trip |
| `tests/test_database_phase19.py` | Static + live-DB coverage | VERIFIED | 8 static tests + 8 live-DB tests, all 16 pass against a real pgvector:pg16 container spun up for this verification (results below) |
| `logic/guild_config.py` | `AmbientSurface` enum + surface-keyed `decide_ambient_channel`/`is_ambient_channel` + `should_welcome_guild` | VERIFIED | All present, module stays `discord`/`datetime`/`random`-free (purity self-check test passes), 22 mock-free tests pass |
| `services/guild_config.py` | Surface-keyed `resolve_ambient_channel`, `home_guild_id`, 4 write-then-invalidate methods | VERIFIED | All present; `set_ambient_roasts_enabled`/`set_vision_roasts_enabled` return `bool` (WR-02 fix); 12 tests pass |
| `tests/test_guild_lifecycle_logic.py` | Mock-free `should_welcome_guild` coverage incl. D-14 fail-closed scar | VERIFIED | File exists, 3 tests pass, includes the named regression test |
| `bot.py` | `on_guild_join`, `on_guild_remove`, boot backfill, home-guild-only startup | VERIFIED | All present; ordering constraint (`seed_home_guild` before `insert_guild_config_if_absent`) holds; CR-01/WR-01/WR-04 fixes all present in source |
| `personality/roasts.py` | `WELCOME_MESSAGES` + `WELCOME_SETUP_HINT` | VERIFIED | Both present; hint names `/setup channel` |
| `cogs/admin.py` | `AdminCog` + `/setup` group (channel/roasts/vision) with inline `manage_guild` gate | VERIFIED | New file, all 3 subcommands present, WR-02/WR-03 fixes present, no `guild`/`guild_id` param anywhere |
| `cogs/help.py` | Admin section listing `/setup` | VERIFIED | `ADMIN_COMMANDS_INFO` + additive "Admin" embed field, names all 3 subcommands |
| `cogs/events.py` | Reaction gate + per-surface split in `on_message` | VERIFIED | `roast_channel_ok`/`vision_channel_ok` present, `in_ambient_channel` retired, reactions gated |
| `cogs/music.py` | `_post_music_roast` routed through the seam | VERIFIED | Confirmed via source inspection |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `database.py SCHEMA_SQL` | `guild_config` | `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` | WIRED | Both ALTERs present with `DEFAULT true`; live-DB confirms pre-existing rows read `true` |
| `load_all_guild_configs` / `seed_guild_config_if_absent` | `guild_config` toggle columns | SELECT column list | WIRED | Both widened; live-DB round trip confirms |
| `cogs/events.py::on_message` | `logic.guild_config.is_ambient_channel` | two independent surface-keyed booleans | WIRED | `roast_channel_ok`/`vision_channel_ok` computed separately, reaction call gated on `roast_channel_ok` |
| `services.guild_config.resolve_ambient_channel` | `logic.guild_config.decide_ambient_channel` | surface passthrough | WIRED | `decide_ambient_channel(config_row=row, surface=surface)` — no re-derived branch |
| `bot.py::_initialize_once boot backfill` | `database.insert_guild_config_if_absent` + `logic.should_welcome_guild` | welcome decision keyed on insert Record | WIRED | Confirmed via source-order assertion + absence of `bot.guild_config.get(` in the backfill welcome path |
| `cogs/music.py::_post_music_roast` | `resolve_ambient_channel(surface=AmbientSurface.ROAST)` | config-seam resolver replacing `_get_text_channel` | WIRED | Confirmed; `_get_text_channel` still used at 6 unrelated command-response sites |
| `cogs/admin.py setup_group` | `app_commands.Group` | Group-level `guild_only` + `default_permissions` | WIRED | Declared once on the Group; zero `@app_commands.guild_only()` decorators on subcommands |
| `cogs/admin.py::setup_channel` | `GuildConfigService.configure_guild_first_time` / `redesignate_guild_channel` | first-configure vs re-designate branch | WIRED | Branches on `cached is None or not cached["configured"]`, read before either write |
| `bot.py::on_guild_remove` | `bot.guild_config._cache` | cache eviction, zero DB writes | WIRED | Confirmed — no `database.` call in the function body |

### Data-Flow Trace (Level 4)

Not applicable in the traditional sense (no dashboard/UI rendering dynamic state), but the equivalent trace — "does the toggle write actually reach the predicate that gates ambient behavior" — was executed directly:

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `decide_ambient_channel` | `config_row["ambient_roasts_enabled"]` / `["vision_roasts_enabled"]` | `GuildConfigService._cache`, refreshed by `_refresh_cache_entry` from the DB helper's `RETURNING` Record | Yes — live-DB round trip confirms a genuine write is visible in the next `resolve_ambient_channel` call via `_refresh_cache_entry` | FLOWING |
| `/setup channel` echo (`_config_echo`) | `self.bot.guild_config.get(...)` post-write | Cache pushed by the service's write-then-invalidate methods | Yes — same Record object returned by the DB `RETURNING` clause is pushed directly, not re-fetched | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full pytest suite (no live DB) | `pytest -q` | 936 passed, 118 skipped, 0 failed | PASS |
| Full pytest suite (live pgvector:pg16 container, spun up for this verification) | `TEST_DATABASE_URL=... pytest -q` | 1054 passed, 0 skipped, 0 failed | PASS |
| Phase 19-specific tests (live DB) | `pytest tests/test_database_phase19.py tests/test_database_phase18.py -v` | 24 passed | PASS |
| Lint | `ruff check .` | All checks passed! | PASS |
| Format | `ruff format --check .` | 112 files already formatted | PASS |
| All modified/created files parse | `python -c "import ast; ast.parse(...)"` | 9/9 files parse cleanly | PASS |
| `AmbientSurface` required-kwarg enforcement | direct call without `surface=` | `TypeError` raised on both `decide_ambient_channel` and `is_ambient_channel` | PASS |
| Toggle-gating semantics | direct calls to `decide_ambient_channel` with various toggle combos | ROAST/PRESENCE silenced by `ambient_roasts_enabled=False` only; VISION silenced by `vision_roasts_enabled=False` only; missing key fails open to `True` | PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` convention or explicit probe declarations found in this phase's PLAN/SUMMARY files. Step 7c: SKIPPED (no probes declared or discovered for this phase — this is a Discord-bot feature phase, not a migration/tooling phase with probe scripts).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|--------------|-------------|-------------|--------|----------|
| ONBOARD-01 | 19-01, 19-02, 19-03 | Welcome/setup-nudge on join, safely-resolved, never crashes the join; boot backfill for offline invites | SATISFIED | `on_guild_join` + boot backfill + `should_welcome_guild` all verified above |
| ONBOARD-02 | 19-04 | `/setup` inline `manage_guild` gate, `default_permissions` is UI-hint only | SATISFIED | `_require_guild_admin` verified as first statement of every subcommand, checks `interaction.permissions.manage_guild` |
| ONBOARD-03 | 19-04 | Channel dropdown picker, not raw argument | SATISFIED (code); dropdown *rendering* is Manual-Only per 19-CONTEXT.md's explicit verifier note | Typed `discord.TextChannel` parameter confirmed |
| ONBOARD-04 | 19-01, 19-02, 19-04 | Independent ambient/vision toggles | SATISFIED | Schema, pure gate, service, and `/setup roasts`/`/setup vision` all verified |
| ONBOARD-05 | 19-03 | Owner notified in `ERROR_LOG_CHANNEL_ID` on join/remove | SATISFIED (code); live delivery is Manual-Only | `_build_guild_notice_embed` + both handlers verified |

**No orphaned requirements** — all 5 ONBOARD-01..05 IDs declared across the 4 plans' `requirements:` frontmatter fields are present in `.planning/REQUIREMENTS.md`'s ONBOARD section and are traced to supporting code above.

### Anti-Patterns Found

Scanned all 9 files touched/created by this phase (`database.py`, `bot.py`, `cogs/admin.py`, `cogs/events.py`, `cogs/help.py`, `cogs/music.py`, `logic/guild_config.py`, `personality/roasts.py`, `services/guild_config.py`) for `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers and empty-implementation patterns.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | — | — | None found. All "placeholder" string matches are legitimate `.format()`-style copy placeholders (e.g. `{name}`) documented in code comments, not stub markers. |

No debt markers, no empty-return stubs, no hardcoded-empty data flowing to rendering in any of the 9 files.

### Code Review Findings (19-REVIEW.md / 19-REVIEW-FIX.md)

The independent code review found 1 blocker (CR-01: `on_guild_join` failed to refresh the cache for a re-invited guild, silently un-configuring it and corrupting a subsequent `/setup channel` first-configure/re-designate branch) and 4 warnings (WR-01 misleading boot-backfill summary, WR-02 silent no-op toggle writes, WR-03 incomplete `view_channel` permission check, WR-04 missing failure isolation in `on_guild_join`). All 5 were independently re-verified as fixed in the current codebase during this verification pass (see Observable Truths #4, #9, #10, #17 above and the direct source reads of `bot.py`, `database.py`, `services/guild_config.py`, `cogs/admin.py`).

### Human Verification Required

The following are parked as Manual-Only per `19-VALIDATION.md`, consistent with the project's standing precedent (Phases 11/13/14/15/16/17/18) that live-Discord and live-DB-against-Neon behavior cannot be asserted from static code. All code-level equivalents of these checks passed above.

### 1. Native channel dropdown rendering

**Test:** In a second test guild, invoke `/setup channel` and observe the client's UI.
**Expected:** The client renders a searchable channel dropdown, not a free-text field.
**Why human:** Client-side rendering has no server-side API surface to assert against; source-verified in discord.py 2.7.1 for a typed `discord.TextChannel` parameter, but only a real client proves the pixel.

### 2. Non-admin ephemeral refusal

**Test:** With a real second Discord account lacking `manage_guild`, run `/setup channel`, `/setup roasts`, and `/setup vision`.
**Expected:** All three refuse ephemerally, before any state change.
**Why human:** Requires a real second Discord account; Discord-interaction mocking is out of convention for this codebase (D-26).

### 3. Live join welcome + ambient activation

**Test:** Invite Dexter to a fresh guild while it is running. Confirm the welcome lands and names `/setup channel`. Confirm silence before `/setup`, ambient roasts after `/setup channel`, and vision roasts only after `/setup vision on`.
**Expected:** Welcome posts once; guild stays silent until configured; vision stays off until explicitly enabled (D-19).
**Why human:** Needs a genuine `on_guild_join` event against Discord's real gateway.

### 4. Boot backfill welcomes exactly once

**Test:** Invite Dexter to a fresh guild with the bot stopped. Start the bot — the welcome must post. Restart the bot — the welcome must NOT post again.
**Expected:** Exactly one welcome across both boots.
**Why human:** The entire point of this feature is that the gateway join event never fired; only a real offline-invite reproduces it.

### 5. Owner join/remove notices

**Test:** Join and then kick Dexter from a test guild.
**Expected:** Both embeds arrive in `ERROR_LOG_CHANNEL_ID`, the guild id is selectable as copy-pasteable text, and the join embed reports whether the welcome posted.
**Why human:** Requires the real error-log channel and a real join/leave event.

### 6. Home-guild regression (D-20 / CONFIG-05)

**Test:** In the home guild, post an image and confirm vision roasts still fire at the pre-Phase-19 cadence. Confirm `/setup vision` reports `on` without anyone having enabled it.
**Expected:** Byte-identical pre/post-Phase-19 behavior in the home guild.
**Why human:** The regression is a silence — invisible to any static code assertion once the column default is confirmed correct (which it was, live-DB-verified above); only a real image-roast cadence check over time proves the runtime claim.

### Gaps Summary

No code-level gaps found. The one blocker (CR-01) and four warnings (WR-01..04) identified by the independent code review were all fixed and independently re-verified against the current codebase during this pass — not merely trusted from 19-REVIEW-FIX.md's claims. The full suite (936/118/0 without a live DB, 1054/0/0 against a real pgvector:pg16 container spun up specifically for this verification) and `ruff check .`/`ruff format --check .` all pass cleanly.

Status is `human_needed` rather than `passed` solely because 6 Manual-Only checks (client-rendered UI, a live non-admin refusal, live join/backfill/remove Discord events, and the home-guild runtime regression check) cannot be asserted from static code — this exactly matches the project's own standing precedent for every prior v1.3/v1.4 phase (11, 13, 14, 15, 16, 17, 18) and is not a deficiency unique to this phase's execution.

---

_Verified: 2026-07-10_
_Verifier: Claude (gsd-verifier)_
