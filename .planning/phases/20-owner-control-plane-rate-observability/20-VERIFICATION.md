---
phase: 20-owner-control-plane-rate-observability
verified: 2026-07-14T00:00:00Z
status: human_needed
score: 7/7 must-haves verified
overrides_applied: 0
human_verification:
  - test: "/guilds list renders one row per guild (name, backtick guild_id, member count, status flags, session AI calls) sorted usage-descending, paginated, ephemeral"
    expected: "Fleet view is readable, sorted with the highest-usage guild first, and no data is truncated silently across pages"
    why_human: "Visual/UX rendering in a live Discord client; cannot be verified by static analysis"
  - test: "Non-owner runs any slash command in a guild the owner has silenced or blocked"
    expected: "Sees the in-persona ephemeral refusal line, never Discord's generic 'application did not respond' failure state"
    why_human: "Requires a live Discord interaction round-trip through interaction_check; behavior depends on real gateway/interaction timing"
  - test: "/guilds block on a guild Dexter is currently in, followed by an owner-initiated re-invite of Dexter to that same guild"
    expected: "Dexter force-leaves immediately on /guilds block (queue/voice teardown observed), and the re-invite causes an immediate silent leave via on_guild_join with no welcome message"
    why_human: "Requires two live Discord guild-membership transitions (leave + re-invite) which cannot be exercised outside a running bot"
  - test: "/guilds silence a guild with active ambient chatter (voice join roasts, proactive callbacks, vision roasts) mid-session"
    expected: "Ambient behavior goes silent on the very next event; a Gemini round-trip already in flight when silence is issued does not produce a stale reply (SC-2)"
    why_human: "Requires real message/voice timing races in a live guild; the pre-send re-check code path is unit-tested but the end-to-end timing race needs a live session to fully trust"
---

# Phase 20: Owner Control Plane & Rate Observability Verification Report

**Phase Goal:** The owner can see every server Dexter is in and can shut off or expel a specific guild the moment it becomes an abuse problem — the reactive half of safety, enforced at one choke point instead of scattered per-cog checks. Plus per-guild AI usage is observable (RATE-01).
**Verified:** 2026-07-14
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | OWNER-01: Owner can list every guild Dexter is in with per-guild AI usage visible | VERIFIED | `cogs/ops.py::guilds_list` (line 410) builds one row per `self.bot.guilds`, sorted by `self.bot.gemini_service.guild_usage(g.id)` descending, backtick-wrapped `guild_id`, member count, status flags, paginated via `GuildListPageView`, ephemeral (`defer(ephemeral=True)`). Structural test `tests/test_guilds_group.py` confirms the group/subcommand shape. |
| 2 | OWNER-02: Owner can silence a guild (stays joined, ambient + commands suppressed) | VERIFIED | `services/guild_config.py::silence_guild/unsilence_guild/is_silenced` (write-then-invalidate, cache-only read); `logic/guild_config.py::decide_ambient_channel` has a `silenced` early-return (`config_row.get("silenced", False)`); `logic/guild_config.py::decide_interaction_allowed` refuses on `silenced`; `cogs/ops.py::guilds_silence/guilds_unsilence` drive it. All confirmed present and exercised by `tests/test_guild_config_logic.py`, `tests/test_guild_config_service.py`, `tests/test_guilds_group.py` (all pass). |
| 3 | OWNER-03: Owner can force-leave a guild with `/stop`-mirroring teardown (no ghost state) | VERIFIED | `cogs/ops.py::_force_leave_teardown` (line 520) bumps `_play_generation`, clears queue, calls `clear_persisted`, stops/disconnects voice, then `target_guild.leave()`, resolved via `bot.get_guild(int(guild_id))` (never `interaction.guild` — Pitfall 3). `guilds_leave` wires it. Structural test asserts the teardown-token sequence and `get_guild` resolution. |
| 4 | OWNER-04: Blocked guilds persist in a blacklist; re-invite is refused | VERIFIED | `database.py` `guild_blocklist` table (own table, D-01) + `load_blocklist`/`insert_blocklist`/`delete_blocklist`; `services/guild_config.py::_blocked` set (O(1), boot-loaded independently) + `block_guild`/`unblock_guild`/`is_blocked`; `bot.py::on_guild_join` checks `bot.guild_config.is_blocked(str(guild.id))` immediately after the boot-race guard and BEFORE `insert_guild_config_if_absent`, calling `guild.leave()` when blocked. Live-DB test `test_blocklist_independent_of_guild_config` proves survival across a `guild_config` delete (Phase 21 purge-proofing). |
| 5 | OWNER-05: One choke point enforces block for slash commands; one seam enforces it for ambient behavior | VERIFIED | `bot.py::DexterCommandTree.interaction_check` is the single pre-dispatch gate for every slash command (`tree_cls=DexterCommandTree` wired in `create_bot`), dispatching on the pure `logic.guild_config.decide_interaction_allowed`. Ambient behavior is silence-aware structurally through `decide_ambient_channel`'s branch, which `is_ambient_channel` (and therefore every ambient surface) dispatches on for free — confirmed no per-cog re-derivation of the block/silence branch anywhere searched. |
| 6 | OWNER-06: Every owner command has an inline `is_owner()` gate; block/silence check is TOCTOU-safe | VERIFIED | `tests/test_guilds_group.py::test_every_guilds_subcommand_opens_with_inline_is_owner_gate` asserts `is_owner(interaction.user)` is the first real statement in all 6 `/guilds` subcommand callbacks (source-grepped). TOCTOU: `cogs/events.py::_maybe_fire_proactive_callback` and `_maybe_fire_vision_roast` both re-invoke `is_ambient_channel` immediately before `message.reply`, confirmed at the exact call sites; `tests/test_proactive_events.py::test_proactive_silenced_mid_flight_no_reply_and_slot_released` and `test_vision_silenced_mid_flight_no_reply` lock the no-stale-response behavior (both pass). |
| 7 | RATE-01: Every Gemini call tagged with `guild_id`; per-guild usage surfaced in `/guilds list` | VERIFIED | `services/gemini.py::_guild_usage` dict + `guild_usage()` accessor; `guild_id` kwarg threaded through `chat()`/`generate_image()`, incremented only when not `None` (guild-less calls and `embed()` correctly excluded, D-09). All non-events call sites (`cogs/ai.py`, `cogs/imagine.py`, `cogs/library.py`, `cogs/music.py`) and the two `cogs/events.py` sites (`_generate_ambient_roast`, `_generate_vision_roast`) pass `guild_id=str(...)`. `cogs/ops.py::guilds_list` reads `guild_usage(g.id)` to sort and render. |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `database.py` | `guild_blocklist` DDL + CRUD + `set_silenced` | VERIFIED | Table at line 227, `set_silenced` at 659, `load_blocklist`/`insert_blocklist`/`delete_blocklist` at 686/704/725 — all present, parameterized (`$N`), inside the single `SCHEMA_SQL` string |
| `logic/guild_config.py` | `silenced` branch + `decide_interaction_allowed` | VERIFIED | Branch at line 116 (`config_row.get("silenced", False)`); `decide_interaction_allowed` at line 197, keyword-only, order is_owner→has_guild→blocked-or-silenced |
| `services/gemini.py` | `guild_id` kwarg + `_guild_usage` + `guild_usage()` | VERIFIED | `_guild_usage` at 166, `guild_usage()` at 178, increment guards at 224/304, `embed()` untouched (no `guild_id` param) |
| `services/guild_config.py` | `_blocked` set + block/unblock/silence/unsilence/is_blocked/is_silenced | VERIFIED | `_blocked` at 58, independent try/except load at ~99-108, all six methods present at 126-174 |
| `cogs/events.py` | TOCTOU pre-send re-check + `guild_id` threading | VERIFIED | Re-checks at lines ~529 (proactive, `AmbientSurface.ROAST`) and ~672 (vision, `AmbientSurface.VISION`); `guild_id=str(member.guild.id)` at 188 and 591 |
| `bot.py` | `DexterCommandTree` + `tree_cls` wiring + block-check-first in `on_guild_join` | VERIFIED | Class at line 79, `tree_cls=DexterCommandTree` at 137, `is_blocked`/`guild.leave()` at 720/726 — positioned before `insert_guild_config_if_absent` (741) |
| `cogs/ops.py` | `/guilds` group (6 subcommands) + `GuildListPageView` + `_parse_guild_id` + `_force_leave_teardown` | VERIFIED | Group at line 400; `guilds_list/silence/unsilence/leave/block/unblock` all present; `_parse_guild_id` at 253; `_force_leave_teardown` at 520 |
| `config.py` | `GUILDS_LIST_PAGE_SIZE` knob | VERIFIED | `GUILDS_LIST_PAGE_SIZE = 1800` present |
| Test files (7) | Structural + unit + live-DB-skippable coverage | VERIFIED | `tests/test_database_phase20.py`, `test_guild_config_logic.py`, `test_guild_config_service.py`, `test_gemini.py`, `test_guilds_group.py`, `test_proactive_events.py`, `test_vision_events.py` — 123 passed / 3 skipped (live-DB, `TEST_DATABASE_URL` unset) when run targeted; full suite reported green by executor (982 passed, 121 skipped, 0 failed) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `DexterCommandTree.interaction_check` | `logic.guild_config.decide_interaction_allowed` | direct call, dispatch on return | WIRED | Confirmed at bot.py:107-119; refusal sent from inside before `return False`, matching the documented discord.py 2.7.1 mechanic |
| `on_guild_join` | `bot.guild_config.is_blocked` | `guild.leave()` on True, before onboarding | WIRED | Confirmed ordering: `is_blocked` check (720) precedes `insert_guild_config_if_absent` (741) |
| `GuildConfigService.load_all` | `database.load_blocklist` | independent try/except populating `_blocked` | WIRED | Confirmed at services/guild_config.py ~99-108; fail-open on blocklist load failure, does not blank config cache |
| `silence_guild`/`unsilence_guild` | `_refresh_cache_entry` | push-invalidate on successful write | WIRED | Confirmed at services/guild_config.py:149-174 |
| `_maybe_fire_proactive_callback`/`_maybe_fire_vision_roast` | `is_ambient_channel` (silence-aware) | re-evaluated immediately before `message.reply` | WIRED | Confirmed at cogs/events.py ~529 and ~672; bail releases reserved slot / skips cooldown mark |
| `/guilds list` | `gemini_service.guild_usage` + `guild_config.get/is_silenced/is_blocked` | one row per `bot.guilds`, sorted desc | WIRED | Confirmed at cogs/ops.py:410-457 |
| `/guilds leave`/`block` | `bot.get_guild(int(guild_id))` | target resolution, never `interaction.guild` | WIRED | Confirmed at cogs/ops.py `guilds_leave`/`guilds_block` bodies; locked by `tests/test_guilds_group.py` source-grep assertions |
| Non-events Gemini call sites (`ai.py`, `imagine.py`, `library.py`, `music.py`) | `gemini_service.chat/generate_image(..., guild_id=...)` | keyword threading | WIRED | Confirmed via 20-03-SUMMARY.md accomplishments + spot-checked `_guild_usage`/`guild_id` signatures in services/gemini.py |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `bot.py` constructs with the custom command tree | `python -c "import bot; b=bot.create_bot(); print(type(b.tree).__name__)"` | `DexterCommandTree` | PASS |
| Phase 20 targeted test files all pass | `pytest tests/test_database_phase20.py tests/test_guild_config_logic.py tests/test_guild_config_service.py tests/test_gemini.py tests/test_guilds_group.py tests/test_proactive_events.py tests/test_vision_events.py -q` | 123 passed, 3 skipped (live-DB, no `TEST_DATABASE_URL`), 0 failed | PASS |
| No debt markers (TBD/FIXME/XXX) in Phase 20 files | `grep -n "TBD\|FIXME\|XXX" bot.py cogs/ops.py cogs/events.py services/gemini.py services/guild_config.py logic/guild_config.py database.py config.py` | no matches | PASS |
| CLAUDE.md schema narrative updated | `grep -n "guild_blocklist\|is_blocked.*DEAD" CLAUDE.md` | `guild_blocklist` table documented, `is_blocked` marked DEAD (D-03) | PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|----------------|--------------|--------|----------|
| OWNER-01 | 20-07 | Owner can list every guild with per-guild AI usage | SATISFIED | `/guilds list` implementation confirmed |
| OWNER-02 | 20-01, 20-02, 20-04, 20-05, 20-06, 20-07 | Owner can silence a guild | SATISFIED | silence_guild/unsilence_guild + silenced branch + choke points confirmed |
| OWNER-03 | 20-07 | Owner can force-leave with teardown discipline | SATISFIED | `_force_leave_teardown` confirmed |
| OWNER-04 | 20-01, 20-04, 20-06, 20-07 | Blocked guilds persist and re-invite is refused | SATISFIED | `guild_blocklist` table + `is_blocked` + `on_guild_join` block-check-first confirmed |
| OWNER-05 | 20-02, 20-06 | Single choke point for commands + ambient behavior | SATISFIED | `DexterCommandTree.interaction_check` + `decide_ambient_channel` silenced branch confirmed |
| OWNER-06 | 20-02, 20-05, 20-06, 20-07 | Inline is_owner() on every owner command; TOCTOU-safe | SATISFIED | structural test + pre-send re-check confirmed |
| RATE-01 | 20-03, 20-05, 20-07 | Every Gemini call tagged with guild_id; usage surfaced | SATISFIED | `guild_id` threading + `guild_usage()` + `/guilds list` confirmed |

No orphaned requirements — REQUIREMENTS.md maps exactly these 7 IDs to Phase 20, all marked `Complete`, all present across the 7 plans' `requirements` frontmatter fields.

### Anti-Patterns Found

Sourced from `20-REVIEW.md` (0 critical / 2 warning / 4 info) and independently spot-checked against the current code — none of these are must-have blockers, but they are real, undismissed findings worth carrying forward:

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `bot.py` | 91-119 (`DexterCommandTree.interaction_check`) | Refusal `send_message` is not guarded by `interaction.type`; `CommandTree._call` invokes `interaction_check` before the autocomplete branch, so a future `@app_commands.autocomplete` handler would raise `HTTPException` for a refused non-owner (WR-01 in 20-REVIEW.md) | WARNING (latent — no autocomplete handler exists today, confirmed by grep for `app_commands.autocomplete` returning nothing) | No current user-facing break; becomes a live trap the moment autocomplete is added to any cog |
| `bot.py` | 110-119 | Refusal copy ("i've been muted...") is identical for both `blocked` and `silenced` branches, and no distinct log line fires for the blocked case (WR-02 in 20-REVIEW.md) | WARNING | Cosmetic/observability gap only — the authorization decision (`False`) is correct in both cases; an operator can't distinguish a stale-block race from an actual silence from behavior alone |
| `services/gemini.py` | 224-226, 304-306 | `_guild_usage` increments right after `_rate_limiter.acquire()`, before the API call — a failed/safety-blocked/empty response is still counted (IN-01) | INFO | "Calls this session" over-reports vs. "successful calls"; acceptable for a budget-hog triage view but worth a doc note |
| `services/gemini.py` / `bot.py` | 163 / `on_guild_remove` | `_guild_usage` entries for departed/blocked guilds are never evicted (IN-02) | INFO | Bounded by distinct-guilds-per-session; cosmetic only |
| `cogs/ops.py` | ~434-437 | `g.member_count` rendered unguarded — can print literal "None members" for an uncached guild (IN-03) | INFO | Untidy output, not a crash |
| `bot.py` | 91-96 | Boot-race fail-open docstring undersells scope — also fails open during the `load_all()` in-flight window (blocklist not yet populated), not just full service absence (IN-04) | INFO | Millisecond-scale boot window; documented as acceptable in the review |

None of the above meet the debt-marker gate (no `TBD`/`FIXME`/`XXX` found) and none are classified `critical` by the code review. They do not block the phase goal today; WR-01/WR-02 are worth a follow-up fix before/alongside the next phase that adds an autocomplete handler.

### Human Verification Required

The following require a live Discord bot/session and cannot be verified by static analysis or the unit-test suite — consistent with every prior v1.3/v1.4 phase's deferred-UAT posture (24/7 host still parked):

### 1. `/guilds list` renders correctly in a live Discord client

**Test:** Run `/guilds list` as the owner in a multi-guild session.
**Expected:** One row per guild, sorted by session AI usage descending, member counts and status flags accurate, pagination works across the char-budget boundary, output is ephemeral.
**Why human:** Visual rendering and pagination UX in a real Discord client.

### 2. Non-owner sees the in-persona ephemeral refusal, not a generic failure

**Test:** A non-owner user runs any slash command in a guild the owner has silenced or blocked.
**Expected:** Sees `"i've been muted in this server. not my call."` ephemerally; never Discord's generic "the application did not respond" error.
**Why human:** Requires a live interaction round-trip through `interaction_check`; the mechanic is code-verified but the actual Discord client-side rendering needs a live check.

### 3. `/guilds block` force-leaves and refuses re-invite

**Test:** Owner runs `/guilds block` on a guild Dexter is currently in (with active voice/queue state), then re-invites Dexter to that guild.
**Expected:** Immediate voice/queue teardown and guild departure on block; the re-invite causes Dexter to silently leave again via `on_guild_join`, with no welcome message and no config row inserted.
**Why human:** Requires two live Discord guild-membership transitions.

### 4. Silence takes effect on ambient chatter already in flight (SC-2)

**Test:** Trigger a proactive callback or vision roast (Gemini round-trip in progress), then issue `/guilds silence` on that guild mid-flight.
**Expected:** No stale reply is sent after the silence lands.
**Why human:** The code path (pre-send re-check) is unit-tested with a mocked mid-flight state change, but the real async timing race benefits from a live confirmation.

### Gaps Summary

No gaps found. All 7 must-have truths (OWNER-01 through OWNER-06, RATE-01) are verified present, substantive, and wired in the codebase — not merely claimed in SUMMARY.md. The two code-review WARNING findings (autocomplete edge case, blocked/silenced refusal-copy conflation) are real but non-blocking: neither breaks any currently-reachable code path, and both are documented in `20-REVIEW.md` for future attention. Phase status is `human_needed` solely because the reactive kill-switch's full value (live guild leave/re-invite, live silence-mid-flight timing, live pagination UX) can only be fully confirmed against a running Discord session — consistent with the project's standing parked-live-UAT posture for every phase since v1.2.

---

_Verified: 2026-07-14_
_Verifier: Claude (gsd-verifier)_
