---
phase: 22-invite-plumbing
verified: 2026-07-14T00:07:05Z
status: human_needed
score: 14/14 must-haves verified (code-level)
overrides_applied: 0
human_verification:
  - test: "Run /invite in a guild the invoker manages, click 'Add to Discord', authorize"
    expected: "Dexter joins the guild, slash commands appear (proving applications.commands scope), and it can join voice + post an embed (proving the permission set is sufficient)"
    why_human: "Requires a live Discord OAuth2 consent flow against a real guild — no CI/unit test can exercise Discord's actual authorization server"
  - test: "Run /invite in a DM with Dexter"
    expected: "The same public embed + 'Add to Discord' button appears, no 'this command can't be used here' refusal"
    why_human: "Requires a live Discord client DM session; guild_only=False is unit-tested but the actual Discord-side DM dispatch behavior is not"
  - test: "Copy /invite's URL, paste into Discord Developer Portal → Dexter → Installation → install link field, re-run /invite, compare byte-for-byte (D-08)"
    expected: "The Developer Portal copy and the in-bot /invite copy are identical"
    why_human: "The Developer Portal install-link field is set by hand in a third-party web UI; no CI can reach it"
  - test: "In the freshly-invited guild: Server Settings → Roles → Dexter"
    expected: "The ten requested permissions (view_channel, send_messages, embed_links, attach_files, add_reactions, read_message_history, connect, speak, create_public_threads, send_messages_in_threads) are present; Administrator / Manage Server / Manage Roles are NOT"
    why_human: "Requires inspecting a live Discord guild's role permissions UI after a real invite-and-join"
---

# Phase 22: Invite Plumbing Verification Report

**Phase Goal:** Anyone can invite Dexter to their own server via a correct, least-privilege invite link — with one source of truth, not hand-maintained duplicates.
**Verified:** 2026-07-14T00:07:05Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | The invite URL requests only the specific permissions Dexter's code provably uses — no Administrator, no Manage Server/Roles (Roadmap SC-1) | ✓ VERIFIED | `config.py:296` `INVITE_PERMISSIONS_VALUE = 309240908864`; `tests/test_invite_logic.py::test_bitfield_excludes_dangerous_permissions` asserts `administrator/manage_guild/manage_roles/manage_channels/ban_members/kick_members` all `False`. Ran `pytest tests/test_invite_logic.py -q` → 10 passed. |
| 2 | The bitfield is exactly `309240908864` — derivable from ten named `discord.Permissions` flags, not a bare magic number | ✓ VERIFIED | `test_bitfield_matches_ten_permission_derivation` constructs the value from the ten keyword flags and asserts equality with `config.INVITE_PERMISSIONS_VALUE`. Ran and passed. |
| 3 | A future silent privilege escalation (e.g. adding `manage_guild`) fails CI (D-02) | ✓ VERIFIED | Negative-assertion test present and passing; test is part of the standard `pytest -q` CI gate (`.github/workflows/ci.yml` runs `pytest -q`, zero secrets). |
| 4 | A single pure function builds the invite URL, requesting `bot` + `applications.commands` scopes | ✓ VERIFIED | `logic/invite.py::build_invite_url()` wraps `discord.utils.oauth_url()`; executed it directly: output is `https://discord.com/oauth2/authorize?client_id=1492588698364018898&scope=bot+applications.commands&permissions=309240908864` — byte-identical to the plan's interface contract. |
| 5 | The client ID resolves with zero secrets in CI (committed public constant + env override) | ✓ VERIFIED | `config.py:278` `DISCORD_CLIENT_ID = int(os.getenv("DISCORD_CLIENT_ID") or "1492588698364018898")`; `test_canonical_url_resolves_without_env_secrets` deletes the env var and still resolves. CI workflow confirmed to set only `TEST_DATABASE_URL`, no Discord secrets. |
| 6 | Running `/invite` returns a public embed with a clickable "Add to Discord" link button (D-05) | ✓ VERIFIED (code) | `cogs/invite.py::invite_command` builds `discord.ui.Button(style=link, url=url, label="Add to Discord")`, sends via `interaction.response.send_message(embed=embed, view=view)` with no `ephemeral=True`. `tests/test_invite_cog.py::test_invite_command_sends_the_canonical_url` + `test_invite_command_is_public_not_ephemeral` pass. Live "does it actually add Dexter to a guild" is human-verify (Roadmap SC-2's outcome half — see Human Verification). |
| 7 | The button's URL is exactly `build_invite_url()`'s output — the cog never hand-builds a URL (D-03) | ✓ VERIFIED | `test_cog_does_not_construct_a_url_itself` (`inspect.getsource` shows no `discord.com/oauth2` literal, no `oauth_url(` call in `cogs/invite.py`); `grep -c "build_invite_url" cogs/invite.py` = 2 (import + call), `grep -c "oauth2/authorize" cogs/invite.py` = 0. |
| 8 | `/invite` works in a DM, not just in a guild (D-06) | ✓ VERIFIED (code) | `InviteCog.invite_command.guild_only is False`, asserted by `test_invite_command_is_dm_allowed`; no `@app_commands.guild_only()` decorator present (`grep -c "guild_only" cogs/invite.py` = 0). Actual DM dispatch is human-verify. |
| 9 | `/invite` is discoverable — it appears in `/help`'s command list | ✓ VERIFIED | `cogs/help.py:23` contains `("/invite", "Get Dexter's invite link")` in `COMMANDS_INFO` (not `ADMIN_COMMANDS_INFO`); `test_invite_listed_in_help_commands` passes. |
| 10 | The invite cog loads on BOTH of `bot.py`'s cog-registration paths (normal startup AND `--first-run` sync) | ✓ VERIFIED | `bot.py:550` `"cogs.invite"` in the `_initialize_once` unconditional tuple (outside the Gemini-gated block); `bot.py:1390` `await bot.load_extension("cogs.invite")` in the `--first-run` sequential block, before the `GEMINI_API_KEY` branch. `test_invite_cog_registered_at_both_bot_load_sites` passes; `grep -c "cogs.invite" bot.py` = 3 (tuple entry, quoted count, load_extension call — ≥2 required). |
| 11 | Every invite URL in a git-tracked public doc literally equals `build_invite_url()`'s output — drift is structurally impossible (D-03/SC-3) | ✓ VERIFIED | `tests/test_invite_drift_guard.py::test_no_doc_contains_a_drifted_invite_url` walks `git ls-files`, excludes `.planning/`, scans `.md/.html/.txt`, and asserts literal equality. Passes today (0 tracked docs carry a link yet — Phase 23 will add one). |
| 12 | The guard's currently-vacuous pass is provably NOT a false green (positive control) | ✓ VERIFIED | `test_drift_guard_actually_detects_a_mismatch` feeds a `tmp_path` doc containing `permissions=8` (literal Administrator) through the real `_collect_offenders` seam and asserts it is caught. Paired with `test_drift_guard_accepts_the_canonical_url` (negative control, zero offenders on the real URL). Both pass. |
| 13 | `.planning/` is excluded from the doc scan, so its `<APP_ID>` placeholder URLs never cause a permanent false-positive (D-10) | ✓ VERIFIED | `test_planning_tree_is_excluded_from_the_scan` positively confirms `.planning/*.md` files exist and are tracked but absent from `_tracked_doc_files()`'s return. Passes. |
| 14 | `logic/invite.py` is the ONLY module in the codebase that constructs an invite URL (D-03/D-07) | ✓ VERIFIED | `test_logic_invite_is_the_only_url_constructor` scans every tracked, non-`tests/`, non-`.planning/` `.py` file for `oauth_url(` / `discord.com/oauth2/authorize`; only `logic/invite.py` may contain either. `test_config_holds_no_url_literal` confirms `config.py` holds no URL literal. Both pass. |

**Score:** 14/14 truths code-verified. All truths that can be checked without a live Discord session are VERIFIED. The two truths whose full outcome depends on a live OAuth2 flow (6 and 8, plus Roadmap SC-1's "granted permissions match" and SC-3's Developer-Portal third copy) are code-complete but have an irreducible human-verification component — see below.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `config.py` | `DISCORD_CLIENT_ID`, `INVITE_PERMISSIONS_VALUE`, `INVITE_SCOPES` | ✓ VERIFIED | All three constants present with exact values specified in the interface contract (lines 278, 296, 300). |
| `logic/invite.py` | `build_invite_url()` — the ONLY invite-URL constructor | ✓ VERIFIED | 68 lines, exports `build_invite_url`, single `discord.utils.oauth_url()` call, module docstring explicitly names the `import discord` deviation. |
| `logic/__init__.py` | Amended package comment naming the one documented exception | ✓ VERIFIED | Lines 1-5 keep the "never discord/asyncio/DB" rule and name `logic/invite.py` as the sole exception. |
| `tests/test_invite_logic.py` | Bitfield derivation lock, D-02 negative lock, URL/scope shape tests | ✓ VERIFIED | 141 lines, 10 tests, all pass. |
| `cogs/invite.py` | `InviteCog` + `/invite` slash command | ✓ VERIFIED | 62 lines, exports `InviteCog`, `setup`; structurally mirrors `cogs/help.py`. |
| `tests/test_invite_cog.py` | Cog-level mocked-interaction tests | ✓ VERIFIED | 164 lines, 8 tests, all pass. |
| `bot.py` (modified) | `cogs.invite` in both registration sites | ✓ VERIFIED WIRED | Confirmed at lines 550 and 1390; both outside the Gemini-gated block. |
| `cogs/help.py` (modified) | `/invite` entry in `COMMANDS_INFO`, not `ADMIN_COMMANDS_INFO` | ✓ VERIFIED WIRED | Line 23. |
| `tests/test_invite_drift_guard.py` | Doc drift guard, positive control, `.planning/` exclusion, single-constructor lock | ✓ VERIFIED | 265 lines, 9 tests, all pass. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `logic/invite.py` | `discord.utils.oauth_url` | the single wrapped library call | ✓ WIRED | `grep -c "discord.utils.oauth_url" logic/invite.py` = 1. Executed and confirmed byte-exact canonical output. |
| `cogs/invite.py` | `logic.invite.build_invite_url` | the only URL source in the cog | ✓ WIRED | Import + one call site; `test_invite_command_sends_the_canonical_url` proves the emitted button URL equals `build_invite_url()`'s output. |
| `bot.py` | `cogs.invite` | both registration sites | ✓ WIRED | Verified at both `_initialize_once` (line 550) and `--first-run` (line 1390). |
| `cogs/help.py` | `/invite` | `COMMANDS_INFO` entry | ✓ WIRED | Line 23, `test_invite_listed_in_help_commands` passes. |
| `tests/test_invite_drift_guard.py` | `logic.invite.build_invite_url` | canonical comparison baseline | ✓ WIRED | `_canonical_url()` helper calls it directly; no hardcoded URL string anywhere in the drift-guard file. |
| `tests/test_invite_drift_guard.py` | `git ls-files` | subprocess enumeration of tracked docs | ✓ WIRED | `_tracked_doc_files` / `_tracked_python_files` both shell out to `git ls-files`; confirmed working via direct execution during this verification. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `build_invite_url()` produces the exact interface-contract URL | `python -c "import config; from logic.invite import build_invite_url; print(build_invite_url(client_id=config.DISCORD_CLIENT_ID, permissions_value=config.INVITE_PERMISSIONS_VALUE, scopes=config.INVITE_SCOPES))"` | `https://discord.com/oauth2/authorize?client_id=1492588698364018898&scope=bot+applications.commands&permissions=309240908864` | ✓ PASS |
| Both `bot.py` cog-registration sites contain `cogs.invite` | `grep -n "cogs.invite" bot.py` | Lines 550 (`_initialize_once` tuple) and 1390 (`--first-run` `load_extension`) | ✓ PASS |
| `/help` lists `/invite` as Utility, not Admin | `grep -n "invite" cogs/help.py` | `("/invite", "Get Dexter's invite link")` in `COMMANDS_INFO` | ✓ PASS |
| Phase's own test files (27 tests: `test_invite_logic.py` + `test_invite_cog.py` + `test_invite_drift_guard.py`) | `pytest tests/test_invite_logic.py tests/test_invite_cog.py tests/test_invite_drift_guard.py -q` | `27 passed` | ✓ PASS |
| Full suite regression check | `pytest -q` | `1035 passed, 124 skipped, 0 failed` | ✓ PASS |
| Lint/format on touched files | `ruff check config.py logic/invite.py logic/__init__.py cogs/invite.py bot.py cogs/help.py tests/test_invite_logic.py tests/test_invite_cog.py tests/test_invite_drift_guard.py` | `All checks passed!` | ✓ PASS |
| Debt-marker scan on all phase-touched files | `grep -n -E "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER"` across all 7 new/modified phase files | No matches | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| INVITE-01 | 22-01 | A least-privilege OAuth2 invite URL exists (explicit `Permissions()` bitfield — no Administrator, no Manage Server/Roles) with `bot` + `applications.commands` scopes | ✓ SATISFIED | `config.INVITE_PERMISSIONS_VALUE`/`INVITE_SCOPES` + `logic/invite.py::build_invite_url()`, locked by 10 passing tests including the D-02 negative assertion. |
| INVITE-02 | 22-02, 22-03 | An in-bot `/invite` command returns the live invite URL as the single source of truth | ✓ SATISFIED | `cogs/invite.py::InviteCog` (`/invite` command, code-verified) + `tests/test_invite_drift_guard.py` (structural single-source-of-truth enforcement, 9 passing tests). |

No orphaned requirements: `.planning/REQUIREMENTS.md` maps only INVITE-01 and INVITE-02 to Phase 22, and both are claimed across the three plans' frontmatter `requirements:` fields.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `cogs/invite.py:39, 278` (config.py) | client_id resolution | WR-01 (code review): `config.DISCORD_CLIENT_ID or self.bot.application_id` — the committed default is always truthy, so the documented "fork fallback" is effectively unreachable unless a fork explicitly sets `DISCORD_CLIENT_ID=0` | ⚠️ Warning (non-blocking) | A fork that clones the repo without setting its own `DISCORD_CLIENT_ID` env var silently promotes the origin bot's invite link, not its own. This matches the exact behavior recorded as "Claude's Discretion" in `22-CONTEXT.md` ("`/invite` falls back to `bot.application_id` if the committed client-ID constant is somehow unset") and is test-locked (`test_invite_command_falls_back_to_application_id`) — the implementation matches the documented decision. Does not block Phase 22's own goal (single-tenant "correct, least-privilege invite for Dexter's own app" is met); relevant to future fork-friendliness, flagged by reviewer, not yet fixed. |
| `cogs/invite.py:39-45` | client_id resolution | WR-02 (code review): `client_id` can theoretically resolve to `None` (`DISCORD_CLIENT_ID=0` AND `bot.application_id is None`), producing a malformed `client_id=None` URL with no validation | ⚠️ Warning (non-blocking) | Edge case requiring two simultaneous unusual conditions; not exercised in the current single-instance deployment where the committed default is always non-zero. |
| `cogs/invite.py:24-27, 57` | `/invite` cooldown | WR-03 (code review): no `@app_commands.checks.cooldown`, unlike `/help`'s 5s cooldown — a public-reply command with no rate limit is a low-grade channel-flood vector | ⚠️ Warning (non-blocking) | Explicitly recorded as "Claude's Discretion" in `22-CONTEXT.md` ("No cooldown on `/invite`... Deliberate departure from `/help`'s 5s cooldown — noted so a reviewer doesn't flag it") and test-locked (`test_invite_command_has_no_cooldown`). Implementation matches the documented, pre-approved decision. |
| `tests/test_invite_drift_guard.py:50` | `TEXT_EXTENSIONS` | IN-01 (code review, info-level): drift guard only scans `.md`/`.html`/`.txt`; a future non-listed text format (`.rst`, `.json`, `.svg`) carrying an invite URL would not be caught | ℹ️ Info | Latent — no such file currently carries a URL. Named as a known, accepted coverage boundary by the reviewer, not an oversight. |

None of the above are blockers: 0 critical findings in the code review (`22-REVIEW.md` frontmatter: `critical: 0, warning: 3, info: 1`). WR-01 and WR-03 both correspond to decisions explicitly pre-recorded in `22-CONTEXT.md`'s "Claude's Discretion" section and locked by passing tests — the code does exactly what the phase's own decision record specifies. They represent a reviewer flagging a *design choice* for reconsideration, not an implementation defect against the phase's must-haves.

### Human Verification Required

Harvested from `22-VALIDATION.md`'s "Manual-Only Verifications" table and `22-02-PLAN.md`'s deferred `<human-check>` blocks (both explicitly deferred to `22-HUMAN-UAT.md` at phase close, per the acknowledged-deferred pattern every phase since 11 has used — blocked on a live Discord host).

### 1. Live invite-and-join flow

**Test:** Run `/invite` in a guild the invoker manages. Click the "Add to Discord" button, select a test guild, authorize.
**Expected:** Dexter joins the guild, slash commands appear (proving the `applications.commands` scope), and it can join voice and post an embed (proving the requested permission set is sufficient).
**Why human:** Requires a live Discord OAuth2 consent flow against a real guild — the code path (button URL correctness) is unit-tested, but Discord's own authorization server behavior cannot be exercised in CI.

### 2. DM usability

**Test:** Run `/invite` in a DM with Dexter (not in a guild).
**Expected:** The same public embed + "Add to Discord" button appears — no "this command can't be used here" refusal.
**Why human:** `guild_only is False` is unit-tested at the command-object level, but the actual Discord-side DM interaction dispatch requires a live client session.

### 3. Developer Portal third-copy comparison (D-08)

**Test:** Copy `/invite`'s URL. In the Discord Developer Portal → Dexter app → Installation, paste it into the install-link field. Re-run `/invite` and compare byte-for-byte.
**Expected:** The two URLs are identical.
**Why human:** The Developer Portal install-link field is a hand-set value in a third-party web UI; no CI or unit test can reach it.

### 4. Granted-permissions confirmation in a live guild (Roadmap SC-1's outcome half)

**Test:** In a freshly-invited guild: Server Settings → Roles → Dexter.
**Expected:** The ten requested permissions (`view_channel`, `send_messages`, `embed_links`, `attach_files`, `add_reactions`, `read_message_history`, `connect`, `speak`, `create_public_threads`, `send_messages_in_threads`) are present, and Administrator / Manage Server / Manage Roles are NOT.
**Why human:** Requires inspecting a live Discord guild's role-permissions UI after a real invite-and-join; the bitfield's *content* is code-locked and unit-tested, but the round-trip through Discord's actual OAuth2 grant is not.

### Gaps Summary

No code-level gaps found. All 14 derived truths (roadmap Success Criteria + all three plans' `must_haves.truths`) are verified against the actual codebase: the ten-permission least-privilege bitfield is CI-locked with both a negative assertion (no escalation) and a positive assertion (no silent capability loss); `build_invite_url()` is the single, pure, tested URL constructor; `/invite` calls it exclusively and is wired into both `bot.py` cog-registration paths and `/help`; and the drift-guard test suite (with a mandatory, verified-working positive control) makes doc-level and Python-level URL duplication structurally fail CI. The full test suite (1035 passed, 124 skipped, 0 failed) and `ruff check`/`ruff format --check` are both clean. Code review found 0 critical issues; its 3 warnings concern a fork-configuration footgun (WR-01) and a flood-control gap (WR-03) that both match decisions explicitly pre-recorded as "Claude's Discretion" in `22-CONTEXT.md` and are locked by passing tests — not defects against this phase's stated must-haves.

Status is `human_needed` rather than `passed` solely because the phase's own Roadmap SC-2 ("a working invite link that successfully adds Dexter to a server") and SC-1's live-permission-grant confirmation have an irreducible live-Discord-OAuth2 component that no unit test can exercise — consistent with every phase since 11's acknowledged-deferred UAT pattern for this codebase. These four items should be captured in `22-HUMAN-UAT.md` at phase close.

---

*Verified: 2026-07-14T00:07:05Z*
*Verifier: Claude (gsd-verifier)*
