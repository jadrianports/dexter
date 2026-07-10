---
phase: 19
slug: onboarding-admin-setup
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-10
---

# Phase 19 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `19-RESEARCH.md` §"Validation Architecture" + §"Security / Threat Model Inputs".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (unpinned, `requirements.txt:8-9`) |
| **Config file** | none — `pyproject.toml` has no `[tool.pytest.ini_options]` section; implicit defaults |
| **Quick run command** | `pytest tests/test_guild_config_logic.py tests/test_guild_config_service.py -x` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | ~15s quick · ~90s full (live-DB tests execute, not skip) |

> **CI note (Phase 18 / D-15):** `.github/workflows/ci.yml` runs `pytest -q` against a
> `pgvector/pgvector:pg16` service container with `TEST_DATABASE_URL` set, so the ~111 live-DB
> tests actually run. Ruff lint **and** format are blocking in the same job. A Phase 19 commit
> that reddens `ruff check .` or `ruff format --check .` fails the gate.

---

## Sampling Rate

- **After every task commit:** `pytest tests/test_guild_config_logic.py tests/test_guild_config_service.py -x`
- **After every plan wave:** `pytest -q`
- **Before `/gsd-verify-work`:** `pytest -q` green **AND** `ruff check .` **AND** `ruff format --check .`
- **Max feedback latency:** ~15 seconds (quick command, mock-free, no DB required)

---

## Phase Requirements → Validation Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| **ONBOARD-01** | `on_guild_join` posts a welcome via `resolve_announce_channel`; a send failure never crashes the join. Boot backfill welcomes **only** newly-inserted guilds (keyed on the `RETURNING` insert result, never the cache — D-14 constraint 2). | mock-free unit (the "should I welcome" decision) + untested-by-design glue | `pytest tests/test_guild_lifecycle_logic.py -x` | ❌ Wave 0 |
| **ONBOARD-02** | `/setup` rejects a non-admin via an **inline** `interaction.permissions.manage_guild` check, first statement, before any data access. `default_permissions` is a UI hint and is never the gate. | untested-by-design (Discord interaction mocking is out of convention per D-26) — structural code review + Manual-Only | n/a (structural review) | n/a |
| **ONBOARD-03** | Channel picker is a typed `channel: discord.TextChannel` slash-command parameter (VERIFIED to render as a native searchable dropdown, discord.py 2.7.1). | untested-by-design (Discord-rendered UI) — structural review asserts the annotation is present | n/a (structural review) | n/a |
| **ONBOARD-04** | `ambient_roasts_enabled` / `vision_roasts_enabled` independently gate `AmbientSurface.ROAST` / `.VISION`. Both columns default `true` (D-20 backward-compat); `/setup channel` writes `vision_roasts_enabled = false` on **first** configure only. | mock-free unit (surface-keyed pure predicate) + live-DB (toggle get/set helpers, column defaults on a pre-existing row) | `pytest tests/test_guild_config_logic.py -x` + `pytest tests/test_database_phase19.py -x` | ❌ Wave 0 (both) |
| **ONBOARD-05** | Owner notified in `ERROR_LOG_CHANNEL_ID` on join and on remove, with a copy-pasteable guild id and the welcome-posted flag. `on_guild_remove` touches **no DB rows** (D-12). | untested-by-design (Discord glue: `log_to_discord`, embed construction) — structural review + clean local boot | n/a (structural review) | n/a |

---

## Per-Task Verification Map

> Populated by `gsd-planner` from the plans it writes. Every task must land an `<automated>`
> verify command from the Sampling Rate section above, or declare a Wave 0 dependency.
> **Continuity rule:** no 3 consecutive tasks without an automated verify.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _(planner fills)_ | | | | | | | | | ⬜ pending |

---

## Wave 0 Requirements

- [ ] **`tests/test_guild_lifecycle_logic.py`** (or folded into `tests/test_guild_config_logic.py`) —
      mock-free coverage of a new pure decision function taking the insert result as a primitive
      (e.g. `should_welcome_guild(*, insert_result: Mapping | None) -> bool`). The DB call and the
      Discord send stay in glue; only the decision is locked. This is the one part of ONBOARD-01
      that genuinely earns a `logic/` seam. **Must include a regression test that an errored /
      empty cache cannot produce a welcome** — the D-14 fail-closed-vs-welcome-spam scar.
- [ ] **`tests/test_database_phase19.py`** — mirrors `tests/test_database_phase18.py`'s structure:
      static source/`SCHEMA_SQL` inspection (both new columns present with `DEFAULT true`; the new
      insert helper uses `ON CONFLICT ... DO NOTHING RETURNING`) **plus** live-DB tests (a genuine
      insert returns a `Record`; a conflicting insert returns `None`; both toggle columns read
      `true` on a row that pre-existed the `ALTER` — the D-20 home-guild-regression lock).
- [ ] **`tests/test_guild_config_logic.py`** — extend for `AmbientSurface`; every existing call to
      `decide_ambient_channel` / `is_ambient_channel` gains the required `surface=` kwarg.
      *(Breaking-change update, not new coverage.)*
- [ ] **`tests/test_guild_config_service.py`** — same `surface=` threading through
      `resolve_ambient_channel`; add `home_guild_id` coverage (set by `seed_home_guild`, `None`
      when `DEXTER_CHANNEL_ID` is unset/unresolvable — the fresh-clone case).
- [ ] **`tests/test_proactive_events.py`** — `bot.guild_config.get()` mocks updated to rows shaped
      for the surface-keyed predicate. Confirmed by research as the complete regression surface;
      `test_autoqueue_playback.py` / `test_now_playing_refresh.py` mock an unrelated
      `_get_text_channel` and **must not** be conflated with it.

No framework install needed — pytest / pytest-asyncio are present; the CI pgvector container
already exists from Phase 18.

---

## Threat Model → Verification

ASVS L1. Threat inputs from `19-RESEARCH.md` §"Security / Threat Model Inputs".

| Ref | Threat | STRIDE | Verification |
|-----|--------|--------|--------------|
| T-19-01 | Permission-check bypass — `default_permissions` treated as the gate | Elevation of Privilege | Structural review: `interaction.permissions.manage_guild` is the **first statement** of every `/setup` subcommand, before any data access (mirrors `cogs/ops.py:252`) |
| T-19-02 | Markdown/embed injection via attacker-chosen `guild.name` into the owner's join/leave embed | Tampering / Spoofing | Structural review: `guild.name` renders as a plain embed field value — never wrapped in markdown, never used as a hyperlink label. Numeric snowflakes (`guild.id`, `owner_id`) go in inline-code spans (they cannot contain a backtick) |
| T-19-03 | Confused deputy — a toggle write or channel designation applied to the wrong guild | EoP / Tampering | Structurally enforced by D-01's subcommand shape: no `/setup` subcommand accepts a `guild`/`guild_id` argument. Every write derives `guild_id` from `interaction.guild.id` only |
| T-19-04 | Welcome-message / owner-notice spam via repeated kick-and-reinvite | Denial of Service | **Explicitly out of Phase 19's mitigation scope** — the blacklist + re-invite refusal is Phase 20's OWNER-04 (D-12). Record as a known limitation for PORT-04 disclosure; do not build a heuristic here (REQUIREMENTS.md lists automated abuse detection as Out of Scope) |
| T-19-05 | TOCTOU on D-06's `send_messages` write-time validation | Tampering | Accepted, self-healing: D-03's silent-skip-with-log already covers a channel that *becomes* unwritable. The check-then-write window is milliseconds; a later revocation is caught by the next ambient send. No new code |

---

## Manual-Only Verifications

Parked behind the always-on residential host, per the standing precedent (Phases 11/13/14/15/16/17).
These become `19-HUMAN-UAT.md` at phase close.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| A typed `channel: discord.TextChannel` parameter renders as a searchable channel dropdown in the Discord client | ONBOARD-03 | Client-side rendering; no API surface to assert against. Source-verified in discord.py 2.7.1, but only a real client proves the pixel | In a second test guild, invoke `/setup channel` and confirm the client offers a channel picker, not a free-text field |
| A non-admin invoking `/setup` gets the in-persona ephemeral refusal | ONBOARD-02 | Requires a real second Discord account with `manage_guild` withheld; Discord-interaction mocking is out of convention (D-26) | With a non-admin account, run each of `/setup channel`, `/setup roasts`, `/setup vision`. All three must refuse, ephemerally, before any state changes |
| Join welcome posts in a real fresh guild, and ambient behavior activates immediately after `/setup channel` | ONBOARD-01, ONBOARD-04 | Needs a genuine `on_guild_join` against Discord's gateway | Invite Dexter to a fresh guild while it is running. Confirm the welcome lands and names `/setup channel`. Confirm silence before `/setup`, ambient roasts after, and vision roasts **only** after `/setup vision on` (D-19) |
| The boot backfill welcomes a guild invited while Dexter was offline — and welcomes it exactly once | ONBOARD-01 | The whole point is that the gateway event never fired; only a real offline-invite reproduces it | Invite Dexter to a fresh guild with the bot stopped. Start the bot: the welcome must post. Restart the bot: the welcome must **not** post again |
| Owner receives the join and remove notices in `ERROR_LOG_CHANNEL_ID` with a copy-pasteable guild id | ONBOARD-05 | Requires the real error-log channel and a real join/leave | Join and then kick Dexter from a test guild. Confirm both embeds arrive, the guild id is selectable as text, and the join embed reports whether the welcome posted |
| The home guild's behavior is byte-identical after the `ALTER` — vision roasting is **not** silently disabled | ONBOARD-04 (D-20 / CONFIG-05) | The regression is a *silence*, invisible to any code assertion once the column default is right | In the home guild, post an image and confirm vision roasts still fire at their pre-Phase-19 cadence. Confirm `/setup vision` reports `on` without anyone having enabled it |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or a declared Wave 0 dependency
- [ ] Sampling continuity: no 3 consecutive tasks without an automated verify
- [ ] Wave 0 covers all ❌ references above
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
