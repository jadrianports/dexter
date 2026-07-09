---
phase: 18-per-guild-config-foundation-ci-gate
verified: 2026-07-10T00:00:00Z
status: human_needed
score: 6/6 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Push the branch and confirm the GitHub Actions `CI` check appears, runs ruff check + ruff format --check + pytest against the pgvector service container, that the ~107 previously-skipped live-DB tests actually RUN (not skip), and that a deliberately-broken commit turns the check red"
    expected: "CI is green on a clean push and turns red on a deliberately broken commit; live-DB tests execute rather than skip"
    why_human: "A workflow YAML's correctness is only observable from GitHub's runner — no push has happened yet, and this cannot be simulated locally without a GitHub Actions environment"
  - test: "Boot the bot against the real Discord token and the real home guild (config.DEXTER_CHANNEL_ID); confirm the startup message posts to the same channel as before the refactor, and that a voice-join roast still fires there"
    expected: "The owner's home guild behaves identically to pre-Phase-18 behavior — same channel, same triggers"
    why_human: "Requires a live Discord connection; the 24/7 host is parked behind the YouTube datacenter-IP block"
  - test: "Invite Dexter to a fresh second guild with no guild_config row; run /play (must work); join voice, post an image, chat in any channel; confirm zero unprompted output and a clean dexter.log"
    expected: "Core commands work immediately; every ambient surface (voice roasts, proactive callbacks, vision roasts, idle/startup messages) stays completely silent"
    why_human: "Requires inviting the bot to a second live guild — not observable from unit/mock tests alone"
  - test: "Revoke send_messages on the configured ambient channel in a live guild; trigger a voice-join roast; confirm no message posts, exactly one WARNING lands in dexter.log, and the guild_config row's configured column is still true"
    expected: "Silent skip, one WARNING log line, row left intact (D-03)"
    why_human: "Requires manipulating real Discord channel permissions live; the unit test (test_resolve_ambient_channel_no_send_perms_returns_none_row_intact) proves the code path but not the live Discord permission-check integration"
---

# Phase 18: Per-Guild Config Foundation & CI Gate — Verification Report

**Phase Goal:** Dexter's ambient/unprompted behavior is driven by real per-guild configuration
instead of one hardcoded channel — the seam every later v1.4 phase reads from — and every
subsequent phase executes behind a green CI gate.
**Verified:** 2026-07-10
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A brand-new guild is completely ambient-silent (no config row) | ✓ VERIFIED | `decide_ambient_channel(config_row=None) -> None` (`logic/guild_config.py:62-63`); `resolve_ambient_channel` returns `None` on a cache miss with **zero discord lookup attempted** (`services/guild_config.py:138-141`, proven by `test_resolve_ambient_channel_cache_miss_returns_none` which makes `guild.get_channel` raise `AssertionError` if ever called); `is_ambient_channel` gates both `on_message` cadences (`cogs/events.py:398-401`) and returns `False` for a `None`/unconfigured row (`test_unconfigured_guild_skips` in `tests/test_proactive_events.py`) |
| 2 | The owner's home guild behaves exactly as before the refactor (seeded from `config.DEXTER_CHANNEL_ID`) | ✓ VERIFIED (code) / **human_needed (live behavior)** | `bot.py:400-433` seeds via `bot.guild_config.seed_home_guild(...)` derived from `bot.get_channel(config.DEXTER_CHANNEL_ID).guild.id`, using the idempotent `ON CONFLICT (guild_id) DO NOTHING` helper (`database.py:451-458`); code-level idempotence proven by live-DB test `test_seed_guild_config_if_absent_is_idempotent` (skips locally, no Postgres). Live-Discord confirmation (same channel, same triggers) requires the real host — parked, see human_verification |
| 3 | Every ambient surface resolves through exactly ONE code path; `bot.py::_resolve_dexter_channel`, `cogs/events.py::_get_ambient_channel`, and both bare-equality `message.channel.id == config.DEXTER_CHANNEL_ID` gates are GONE | ✓ VERIFIED | `grep -n "_resolve_dexter_channel" bot.py` → no match; `grep -n "def _get_ambient_channel" cogs/events.py` → no match; `grep -rn "DEXTER_CHANNEL_ID" cogs/` → **no matches at all** (the env var no longer appears anywhere under `cogs/`); `bot.py:522` and `bot.py:740` both call `bot.guild_config.resolve_ambient_channel(guild)`; `cogs/events.py:222/264/307` (voice sites, sync, no `await`) and `cogs/events.py:398-401/408/415` (both `on_message` gates via `is_ambient_channel`) all route through the single seam |
| 4 | Per-guild config reads never issue a live Neon round-trip during event handling — in-memory cache, loaded at boot, push-invalidated only on change | ✓ VERIFIED | `services/guild_config.py::get()` reads only `self._cache` (no `await`, no pool access); `load_all()` is the single boot round-trip; `_refresh_cache_entry` is the push-invalidate seam, used only by `seed_home_guild`. Directly proven by `test_no_round_trip_after_load_all` — a spy pool asserts `pool.acquire_count == 1` after `load_all()`, even after multiple `get()`/`resolve_ambient_channel()` calls. `load_all()` fail-closed (empty cache, no re-raise) proven by `test_load_all_fails_closed_on_pool_error` / `test_load_all_fails_closed_on_fetch_error` |
| 5 | Every push and PR runs pytest + lint in GitHub Actions (CICD-01); README badge absence is NOT a gap (D-17 defers it to Phase 23) | ✓ VERIFIED (code) / **human_needed (first live run)** | `.github/workflows/ci.yml` triggers on `push:`/`pull_request:` (never `pull_request_target`), top-level `permissions: contents: read`, zero `secrets.*` references, `pgvector/pgvector:pg16` service container + `TEST_DATABASE_URL` env, three blocking steps (`ruff check .`, `ruff format --check .`, `pytest -q`). Locally reproduced: `ruff check .` → 0 findings; `ruff format --check .` → clean; `pytest -q` → 877 passed / 111 skipped / 0 failed. No README badge present — correctly deferred per D-17/ROADMAP SC-5, not a gap. First actual GitHub Actions run is unobserved (nothing pushed) — parked, see human_verification |

**Score:** 5/5 ROADMAP Success Criteria code-verified (2 carry a parked live-observation component, tracked as human_verification, not a gap)

### Requirement-Level Detail (CONFIG-03 — flagged for verifier judgment)

REQUIREMENTS.md showed CONFIG-03 as `Pending` while its sibling requirements were `Complete`. Verified directly against the codebase (not rubber-stamped):

- `GuildConfigService.load_all()` performs exactly ONE `database.load_all_guild_configs(pool)` call at boot, rebuilding `self._cache` keyed by `str(guild_id)` — fails closed (cache left `{}`, no re-raise) on any exception (`services/guild_config.py:63-86`).
- `GuildConfigService.get()` is a synchronous, zero-`await`, cache-only dict read (`services/guild_config.py:88-90`).
- `GuildConfigService.resolve_ambient_channel()` is `def` (not `async def`) and only ever calls `self.get(guild.id)` — no pool access, confirmed structurally (no `self.pool` reference anywhere in the method body) and behaviorally by `test_no_round_trip_after_load_all`, which asserts `pool.acquire_count == 1` (the one `load_all()` call) even after two `get()` calls and two `resolve_ambient_channel()` calls.
- Push-invalidation exists (`_refresh_cache_entry`) and is exercised by `seed_home_guild` — the only writer Phase 18 ships (Phase 19/20 add the remaining writers per D-11/D-13).

**Verdict: CONFIG-03 is genuinely delivered.** REQUIREMENTS.md has been updated (`.planning/REQUIREMENTS.md`, both the requirement-list checkbox and the traceability table row) to reflect `Complete` — this was a documentation-sync gap, not a code gap.

### Code Review Fix Verification (18-REVIEW.md — re-verified independently, not trusted from SUMMARY)

| Finding | Claimed Fix | Independently Verified |
|---------|-------------|------------------------|
| BL-01 (CRITICAL): CI's `TEST_DATABASE_URL` byte-identical to the tests' own "unconfigured" sentinel → 12 live-DB tests silently skipped in CI despite a real Postgres being available | Changed skip-guard to `os.getenv("TEST_DATABASE_URL") is None` (presence check) in all 4 affected files | ✓ CONFIRMED — `grep` shows all 4 files (`test_database_phase{11,15,16,18}.py`) now use `_SKIP_LIVE = os.getenv("TEST_DATABASE_URL") is None`. Reproduced the exact CI env value locally: with `TEST_DATABASE_URL` set to the literal CI string, the 3 `test_database_phase18.py` live tests are no longer skipped by the `_SKIP_LIVE` marker — they attempt a real connection and skip only via the `pool` fixture's own "Postgres unavailable" path (`password authentication failed` — expected, no local Postgres running). This proves the fix holds: given a real reachable Postgres (as CI's pgvector service provides), these tests would now execute. |
| WR-01: `decide_ambient_channel` could raise uncaught on a malformed `ambient_channel_id` | `int(channel_id)` wrapped in `try/except (TypeError, ValueError): return None` | ✓ CONFIRMED — `logic/guild_config.py:71-74`; locked by `test_malformed_channel_id_empty_string_returns_none` / `test_malformed_channel_id_non_numeric_string_returns_none` / `test_malformed_channel_id_returns_false` in `tests/test_guild_config_logic.py` |
| WR-02: duplicate `is_ambient_channel` gate computation in `on_message` | Compute `in_ambient_channel` once, reuse for both cadences | ✓ CONFIRMED — `cogs/events.py:398-416`; single `is_ambient_channel(...)` call feeding both the proactive (`if in_ambient_channel`) and vision (`if in_ambient_channel and message.attachments`) gates, which remain independent conditionals (not merged) |
| WR-03: `_post_startup_messages` aborted posting to remaining guilds on one guild's send failure | Move `try/except` inside the per-guild loop | ✓ CONFIRMED — `bot.py:520-529`; `try/except Exception: log.warning(...)` now lives inside the `for guild in bot.guilds:` loop body |

All four review findings are genuinely fixed with dedicated commits (`9a4a6ea`, `1a85e33`, `57467d1`, `f66a5b0`) and test coverage — not merely claimed in SUMMARY.md.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `database.py` (`guild_config` DDL) | 7-column table, `guild_jams`/`resolution_cache` idiom | ✓ VERIFIED | `guild_id TEXT PK`, `ambient_channel_id TEXT`, `configured/silenced/is_blocked BOOLEAN NOT NULL DEFAULT false`, `joined_at/updated_at TIMESTAMPTZ` (`database.py:204-212`); no `ambient_roasts_enabled`/`vision_roasts_enabled` (correctly deferred to Phase 19, D-12) |
| `database.py::load_all_guild_configs` / `seed_guild_config_if_absent` | Boot load-all + idempotent seed, `$N` params only | ✓ VERIFIED | Both use positional `$N` params; seed uses `ON CONFLICT (guild_id) DO NOTHING`, no `DO UPDATE` anywhere (`database.py:403-464`) |
| `logic/guild_config.py` | Pure `decide_ambient_channel` + `is_ambient_channel`, no discord/asyncio/datetime/random | ✓ VERIFIED | Confirmed by direct read — imports only `from typing import Mapping`; both functions keyword-only |
| `services/guild_config.py::GuildConfigService` | Cache + both named resolvers | ✓ VERIFIED | `load_all`, `get`, `_refresh_cache_entry`, `seed_home_guild`, `resolve_ambient_channel` (sync), `resolve_announce_channel` (sync, zero production callers — confirmed via `grep -rn resolve_announce_channel` returning only its own definition + tests) |
| `bot.py` boot wiring | Constructs service, loads cache, seeds home guild | ✓ VERIFIED | `bot.py:406-433`, inside `_initialize_once`, after `log_to_discord` wiring, before cog-load loop; unset/unresolvable `DEXTER_CHANNEL_ID` → `log.info` skip, no raise (D-10) |
| `cogs/events.py` consolidation | 3 voice sites + 2 gates routed; zero `DEXTER_CHANNEL_ID` | ✓ VERIFIED | `grep -rn DEXTER_CHANNEL_ID cogs/` → empty; 3 sync `resolve_ambient_channel` calls; both gates via `is_ambient_channel` |
| `.github/workflows/ci.yml` | pytest + Ruff, pgvector container, least-privilege | ✓ VERIFIED | `pull_request` (not `_target`), `permissions: contents: read`, `pgvector/pgvector:pg16`, `TEST_DATABASE_URL`, 3 blocking steps, zero secrets, zero `GEMINI_API_KEY` |
| `pyproject.toml` / `requirements-dev.txt` | Ruff config + dev pin | ✓ VERIFIED | `[tool.ruff]` target py311, line-length 120, `select = ["E","F","W","I"]`; `ruff>=0.15,<0.16` dev-only |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `bot.py::_post_startup_messages` / `idle_check` | `GuildConfigService.resolve_ambient_channel` | sync call, no `await` | ✓ WIRED | Confirmed at `bot.py:522`, `bot.py:740` |
| `cogs/events.py` voice sites (3) | `GuildConfigService.resolve_ambient_channel` | sync call | ✓ WIRED | `cogs/events.py:222,264,307` |
| `cogs/events.py::on_message` (2 gates) | `logic.guild_config.is_ambient_channel` | predicate over `self.bot.guild_config.get(...)` | ✓ WIRED | `cogs/events.py:398-401`; vision gate keeps `message.attachments` and stays a separate `if` |
| `services/guild_config.py::seed_home_guild` | `database.seed_guild_config_if_absent` | await + `_refresh_cache_entry` | ✓ WIRED | `services/guild_config.py:104-118` |
| `.github/workflows/ci.yml` | `tests/conftest.py` pool fixture | `TEST_DATABASE_URL` + pgvector-codec-registering fixture | ✓ WIRED | conftest registers `register_vector` extension-first (`tests/conftest.py:50-57`), matching `bot.py::_initialize_once`'s ordering |

### Data-Flow Trace (Level 4)

Not applicable in the UI-rendering sense (no dynamic frontend); the equivalent trace for this phase is the CONFIG-03 no-round-trip proof above, which traces `resolve_ambient_channel` → `get()` → `self._cache` (populated once by `load_all()` → `database.load_all_guild_configs`) and confirms no live path bypasses the cache. Confirmed FLOWING (cache-backed, boot-loaded, no bypass).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Ruff lint clean | `ruff check .` | "All checks passed!" | ✓ PASS |
| Ruff format clean | `ruff format --check .` | "108 files already formatted" | ✓ PASS |
| Full suite green | `pytest -q` | 877 passed, 111 skipped, 0 failed | ✓ PASS |
| CR-01 fix holds under CI's exact env value | `TEST_DATABASE_URL="postgresql://dexter:dexter@localhost:5432/dexter_test" pytest -q tests/test_database_phase18.py -rs` | 6 passed, 3 skipped — skip reason is now "Postgres unavailable (password authentication failed...)" from the `pool` fixture, NOT the old `_SKIP_LIVE` sentinel match | ✓ PASS |
| Guild-config seam test suite | `pytest -q tests/test_guild_config_logic.py tests/test_guild_config_service.py tests/test_database_phase18.py tests/test_proactive_events.py tests/test_vision_events.py tests/test_ambient_recall_cadence.py` | 59 passed, 3 skipped (live-DB, expected) | ✓ PASS |
| No debt markers in phase-18 files | `grep -rn "TBD\|FIXME\|XXX"` across all phase-18-touched files | no matches | ✓ PASS |

### Probe Execution

N/A — no `scripts/*/tests/probe-*.sh` convention used by this phase; verification relies on pytest + ruff (both run directly above).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| CONFIG-01 | 18-02 | `guild_config` table, 7 columns | ✓ SATISFIED | `database.py:204-212` |
| CONFIG-02 | 18-03/18-04/18-05/18-06 | One consolidated resolver, both bare-equality gates gone | ✓ SATISFIED | grep evidence above, all call sites repointed |
| CONFIG-03 | 18-04/18-05 | Cache-only reads, boot load, push-invalidate | ✓ SATISFIED (see Requirement-Level Detail above; REQUIREMENTS.md corrected) |
| CONFIG-04 | 18-03/18-05/18-06 | Ambient default-off for unconfigured guilds | ✓ SATISFIED | `test_unconfigured_guild_skips`, `test_resolve_ambient_channel_cache_miss_returns_none` |
| CONFIG-05 | 18-02/18-04/18-05 | Idempotent home-guild seed | ✓ SATISFIED | `ON CONFLICT (guild_id) DO NOTHING`, `test_seed_guild_config_if_absent_is_idempotent` (live-DB, skips locally) |
| CICD-01 | 18-01/18-02/18-07 | CI gate: pytest + lint, blocking, on push+PR | ✓ SATISFIED (code) — badge correctly deferred to Phase 23 per D-17/SC-5, not a gap | `.github/workflows/ci.yml` |

No orphaned requirements found — REQUIREMENTS.md's Phase 18 row set (CONFIG-01..05, CICD-01) matches exactly what the 7 plans' frontmatter `requirements:` fields declare in aggregate.

### Anti-Patterns Found

None. No `TBD`/`FIXME`/`XXX`/`HACK`/`PLACEHOLDER` markers, no empty stub implementations, and no hardcoded-empty-data patterns found in any phase-18-touched file (`database.py`, `logic/guild_config.py`, `services/guild_config.py`, `bot.py`, `cogs/events.py`, `.github/workflows/ci.yml`, `pyproject.toml`, and the new test files).

### Human Verification Required

See frontmatter `human_verification` list. Summary: 4 items, all parked behind the same "24/7 host is parked" constraint that governed Phases 11/13/14/15/16/17 — the first real GitHub Actions run, the home-guild live-behavior check, the fresh-second-guild silence check, and the stale-channel silent-skip check. All 4 have full code-level coverage (unit/mock tests proving the underlying logic) and are blocked only on a live Discord connection / a git push, neither of which is available in this environment.

### Gaps Summary

No code-level gaps found. All 5 ROADMAP Success Criteria are satisfied at the code level; all 6 phase requirements (CONFIG-01..05, CICD-01) are genuinely delivered, including CONFIG-03 which REQUIREMENTS.md had left as `Pending` pending verifier judgment — corrected to `Complete` in this pass after independent confirmation (no rubber-stamping). All 4 code-review findings (1 critical, 3 warnings) from `18-REVIEW.md` were independently re-verified as genuinely fixed, not merely claimed. The only outstanding items are the 4 live-Discord/live-CI-runner checks that no phase since Phase 11 has been able to close locally, for the same standing reason (parked 24/7 host).

---

_Verified: 2026-07-10_
_Verifier: Claude (gsd-verifier)_
