# Phase 18: Per-Guild Config Foundation & CI Gate - Research

**Researched:** 2026-07-10
**Domain:** Postgres schema seam (asyncpg/Neon idiom) + discord.py service/cog wiring + GitHub Actions CI (pytest + Ruff, pgvector service container)
**Confidence:** HIGH (all findings verified against the actual repo files, current line numbers, and a live local ruff/pytest run — no speculative claims)

## Summary

This phase is a pure refactor-and-infrastructure phase: no new user-facing behavior, no new
dependencies except a dev-only lint tool (Ruff) and a CI-only service container
(`pgvector/pgvector:pg16`). Every claim in CONTEXT.md's `<canonical_refs>` about exact file/line
locations was re-verified against the current repo and found accurate to within a line or two
(see Call-Site Inventory). The two functions named in SC-3 (`bot.py::_resolve_dexter_channel`,
`cogs/events.py::_get_ambient_channel`) are byte-identical duplicates — same 4-step fallback body,
same docstring admission that duplication was tolerated "per plan." Six call sites route through
them or through the two bare-equality gates; all six are ambient/unprompted and must switch to a
new **strict** resolver. A third, unrelated fallback resolver (`cogs/music.py::_get_text_channel`)
exists and is explicitly **out of scope** — it resolves the *last-active-music-channel* for
command-triggered posts (auto-lyrics, idle-leave farewell, auto-queue announcements), not the
ambient channel, and CONFIG-02/SC-3 name only the two functions above.

The most consequential research finding is **not** the one CONTEXT.md flagged (a real
`GEMINI_API_KEY` requirement) — none of the ~108 live-DB tests need one; every embedding used in
a live-DB test is a synthetic `[0.1] * config.EMBED_DIM` literal, never a real Gemini call. The
finding that *is* consequential and previously undocumented: **`tests/conftest.py`'s shared `pool`
fixture never registers the pgvector codec** (`pgvector.asyncpg.register_vector`), yet 4 of the 6
live-DB test files that use it (`test_database_phase11.py`, `test_database_phase15.py`,
`test_database_phase16.py`, plus indirectly any future file inserting into `user_memories`) bind a
Python `list[float]` directly into a `vector(768)` column via `database.insert_memory` /
`database.search_memories`. `bot.py`'s own `_initialize_once` docstring describes exactly this
failure mode ("unknown type: public.vector" ValueErrors) and works around it with an
extension-first throwaway connection + `init=_register_vector` on the real pool. The test fixture
has neither. **Standing up the CI pgvector service container without also fixing this fixture will
turn 9 currently-skipped tests into 9 CI failures**, not passes — this must be a Phase 18 task, not
an assumption.

**Primary recommendation:** Build `logic/guild_config.py` (pure) + `services/guild_config.py`
(`GuildConfigService`, I/O + both named resolvers) + a `guild_config` table mirroring the
`guild_jams` idiom; wire cache-load + home-guild-seed into `bot.py::_initialize_once` (inherits
the existing `_ready_done` re-entrancy guard for free — no new guard needed); repoint all 6 ambient
call sites at `bot.guild_config.resolve_ambient_channel`; fix `tests/conftest.py`'s `pool` fixture
to register the vector codec with correct extension-first ordering *before* wiring CI; ship the
Ruff config + one atomic lint-cleanup commit (58 findings in source, ~124 in tests, at
`line-length=120` — very manageable); ship `.github/workflows/ci.yml` with a `pgvector/pgvector:pg16`
service container, `TEST_DATABASE_URL` env, and `permissions: contents: read`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Ambient channel resolution (roasts, callbacks, vision, idle, startup) | API/Backend (service layer: `GuildConfigService`) | Browser/Client (Discord gateway objects consumed) | Decision logic is pure Python (`logic/guild_config.py`); the service owns the cache + DB I/O; cogs are thin dispatchers — matches the existing cog→service→model layering |
| `guild_config` cache (in-memory, boot-loaded) | API/Backend | Database/Storage (source of truth on miss/failure) | CONFIG-03 forbids a per-event DB round-trip; the cache *is* the hot-path read tier, DB is write-through only |
| Home-guild seed | API/Backend (boot sequence in `bot.py`) | Database/Storage | One-time idempotent write at boot, not a request-driven path |
| CI test/lint gate | CI/Build tier (GitHub Actions) | Database/Storage (ephemeral pgvector container, ephemeral only) | Entirely outside the runtime application tiers — a build-time gate, not a runtime capability |
| `guild_config` schema | Database/Storage | — | New table, idempotent DDL, follows `guild_jams`/`resolution_cache` precedent |

## User Constraints (from CONTEXT.md)

### Locked Decisions (D-01 … D-17 — verbatim intent, condensed; see 18-CONTEXT.md for full rationale)

- **D-01:** Ambient resolution is STRICT — `guild_config.ambient_channel_id` row or silence. The
  existing 4-step fallback chain is removed entirely from the ambient path.
- **D-02:** The fallback chain survives as a SECOND, explicitly named resolver,
  `resolve_announce_channel(guild) -> TextChannel | None`, used only by Phase 19's join-welcome and
  owner-facing notices — never by an ambient surface. Two named functions, not one function with a
  boolean flag.
- **D-03:** A stale/unwritable configured channel is a silent skip + `WARNING` log line. The row
  stays intact; `configured` stays `true`.
- **D-04:** The seam is `services/guild_config.py::GuildConfigService`, wired in `bot.py`, attached
  as `bot.guild_config`, reached via `self.bot.guild_config` from cogs.
- **D-05:** Extract a pure `logic/guild_config.py` — keyword-only, `discord`-free, `datetime`-free.
  The service does I/O; the pure function decides; glue dispatches on the return value.
- **D-06:** Load-all at boot (`SELECT * FROM guild_config` once). A cache MISS is authoritative —
  no DB read, no round-trip, ever, in the hot path.
- **D-07:** FAIL CLOSED. Boot-load failure or write-throw → every guild reads as unconfigured;
  core commands keep working; error surfaces to `dexter.log` + `ERROR_LOG_CHANNEL_ID`.
- **D-08:** An idempotent one-time boot seed: resolve `bot.get_channel(DEXTER_CHANNEL_ID)` →
  `ch.guild.id`, then `INSERT ... ON CONFLICT (guild_id) DO NOTHING` with `configured = true`,
  refresh that one cache entry. Safe to re-run every boot forever.
- **D-09:** `ON CONFLICT DO NOTHING`, never `DO UPDATE` — the env var is bootstrap-only, no ongoing
  authority once the row exists.
- **D-10:** An unset/unresolvable `DEXTER_CHANNEL_ID` is a silent INFO skip, not an error, not a
  boot-refusal.
- **D-11:** Create `silenced` + `is_blocked` columns now; read them in NO Phase 18 code (Phase 20's
  job).
- **D-12:** Phase 19 adds `ambient_roasts_enabled` / `vision_roasts_enabled` via
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` — not Phase 18's job.
- **D-13:** Phase 18 ships NO way to configure a second guild — no stopgap owner-only setter.
- **D-14:** Ruff (lint + format check) — single tool, near-default ruleset, tighten later not now.
- **D-15:** CI stands up a `pgvector/pgvector:pg16` service container + `TEST_DATABASE_URL`,
  unskipping the live-DB tests with zero secrets/zero Neon traffic. **Researcher must confirm no
  skipped test needs a real `GEMINI_API_KEY`.** (Confirmed — see Open Questions, resolved.)
- **D-16:** Both pytest and Ruff are BLOCKING. The lint/format cleanup is its OWN atomic commit,
  separate from the config-seam refactor.
- **D-17:** The README build badge lands in Phase 23, not Phase 18.

### Claude's Discretion (do NOT re-ask the user — planner decides, informed by this research)

- Exact `guild_config` schema types/defaults/index/`updated_at` handling (research proposes a
  concrete DDL below, following `guild_jams`).
- Cache data structure — `dict[str, asyncpg.Record]` vs a frozen dataclass in `models/` (research
  recommends a `models/guild_config.py::GuildConfig` frozen dataclass, mirroring
  `models/memory.py::MemoryFact` — see Code Examples).
- Exact pure-function signatures/count in `logic/guild_config.py` (research proposes two:
  `decide_ambient_channel` + `is_ambient_channel`).
- Where the boot seed runs (research recommends: inside `_initialize_once`, immediately after pool
  creation and before cog loading — see Boot Ordering below).
- Ruff ruleset contents/target-version/per-file ignores/`--check` vs `--diff` (research proposes a
  concrete config below, sized against a live local run).
- Workflow YAML job/matrix layout (research proposes a concrete example below).
- Which ambient surfaces need touching (research's Call-Site Inventory below is the exhaustive
  answer, verified line-by-line against the current repo, not the CONTEXT.md grep-was-a-starting-point).

### Deferred Ideas (OUT OF SCOPE for Phase 18)

- `/setup` + channel dropdown picker (Phase 19, ONBOARD-02/03).
- `ambient_roasts_enabled` / `vision_roasts_enabled` toggle columns (Phase 19, ONBOARD-04).
- Readers/setters for `silenced` / `is_blocked`, `CommandTree.interaction_check` enforcement, owner
  control plane (Phase 20).
- `on_guild_join` / `on_guild_remove` lifecycle handlers (Phase 19 welcome, Phase 21 MEM-04 purge).
- README build badge (Phase 23).
- GitHub Pages CD + GHCR image publish (Phase 23, CICD-02/03).
- Tightening the Ruff ruleset beyond near-default (later cleanup, not a Phase 18 blocker).
- `cogs/music.py::_get_text_channel` (the "last active music channel" resolver) — **not named by
  CONFIG-02/SC-3**, serves command-triggered posts (auto-lyrics, idle-leave, auto-queue), not
  ambient/unprompted surfaces. Do not touch.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CONFIG-01 | `guild_config` table (`guild_id` PK, `ambient_channel_id`, `configured`, `silenced`, `is_blocked`, `joined_at`, `updated_at`) in `SCHEMA_SQL`, following `guild_jams`/`resolution_cache` idiom | Exact DDL proposed below; verified `guild_jams` (database.py:188-197) + `resolution_cache` (178-186) as structural analogs; asyncpg multi-statement DDL rule confirmed (`init_db` runs `SCHEMA_SQL` in one `conn.execute()`, no `$N` params) |
| CONFIG-02 | One consolidated resolver replaces `bot.py::_resolve_dexter_channel`, `cogs/events.py::_get_ambient_channel`, and the two bare-equality gates | Exhaustive Call-Site Inventory below (6 sites, verified line numbers); pure-predicate design (`logic/guild_config.py::is_ambient_channel`) replaces both bare-equality gates without duplicating branch logic in the caller |
| CONFIG-03 | `GuildConfigService` in-memory cache, boot-loaded, push-invalidated, never a per-event round-trip | `GuildConfigService` skeleton below; `services/memory.py` + `services/metrics.py` wiring pattern confirmed as the template; cache-miss-is-authoritative design verified against D-06 |
| CONFIG-04 | Ambient surfaces silent until `/setup`; core commands work immediately | Structural property of `decide_ambient_channel` returning `None` on cache miss — verified no DB read occurs on miss (D-06); confirmed `/play`/`/ask`/etc. never call the ambient resolver |
| CONFIG-05 | Home guild seeded from `config.DEXTER_CHANNEL_ID`, current behavior unchanged | Boot-ordering trace below confirms `bot.get_channel()` resolves correctly inside `on_ready`/`_initialize_once` (guild+channel caches populated before `on_ready` fires per official discord.py docs) |
| CICD-01 | GitHub Actions runs pytest + lint on every push/PR | Concrete workflow YAML below; pgvector codec-registration gap in `tests/conftest.py` identified as a MUST-FIX prerequisite (not previously documented); Ruff findings sized via a live local run (58 source / ~124 test findings at line-length=120) |
</phase_requirements>

## Call-Site Inventory

Verified by direct read of `bot.py` and `cogs/events.py` at their current line numbers (2026-07-10).
CONTEXT.md's line numbers were accurate to within 1-2 lines in every case.

| File:Line | Surface | Currently posts via | Ambient? | New resolver call |
|-----------|---------|---------------------|----------|--------------------|
| `bot.py:103-143` | `_resolve_dexter_channel` (the function itself) | 4-step fallback chain body | N/A — function body | Becomes `resolve_announce_channel`'s body (D-02); function deleted from `bot.py` |
| `bot.py:515` | Startup message (`_post_startup_messages`) | `_resolve_dexter_channel(guild)` | **YES** — CONFIG-04 explicitly lists "startup messages" as an ambient surface that must go silent | `bot.guild_config.resolve_ambient_channel(guild)` |
| `bot.py:739` | Idle-loneliness message (`idle_check` loop) | `_resolve_dexter_channel(guild)` | **YES** — CONFIG-04 explicitly lists "idle messages" | `bot.guild_config.resolve_ambient_channel(guild)` |
| `cogs/events.py:98-137` | `_get_ambient_channel` (the function itself) | 4-step fallback chain body, byte-identical to `bot.py`'s | N/A — function body | Deleted entirely; `EventsCog` calls `self.bot.guild_config.resolve_ambient_channel` instead |
| `cogs/events.py:266` | Bot-moved-channel complaint (`on_voice_state_update`) | `self._get_ambient_channel(member.guild)` | **YES** — unprompted personality reaction | `self.bot.guild_config.resolve_ambient_channel(member.guild)` |
| `cogs/events.py:310` | Voice-join roast / late-night roast | `self._get_ambient_channel(guild)` | **YES** — CONFIG-04 "roasts" | same |
| `cogs/events.py:356` | Voice-leave roast | `self._get_ambient_channel(guild)` | **YES** — CONFIG-04 "roasts" | same |
| `cogs/events.py:443-446` | Bare-equality gate #1 — proactive-callback dispatch (`on_message`) | `message.channel.id == config.DEXTER_CHANNEL_ID` | **YES** — CONFIG-04 "proactive callbacks" | `logic.guild_config.is_ambient_channel(config_row=self.bot.guild_config.get(message.guild.id), channel_id=message.channel.id)` |
| `cogs/events.py:454-457` | Bare-equality gate #2 — vision-roast dispatch (`on_message`) | `message.channel.id == config.DEXTER_CHANNEL_ID` (+ `message.attachments`) | **YES** — CONFIG-04 "vision roasts" | same predicate as above |

**Six live ambient call sites total** (2 in `bot.py`, 4 in `cogs/events.py`), consolidating onto
one strict resolver + one predicate. Both duplicated fallback-chain *functions* (`bot.py:103-143`,
`cogs/events.py:98-137`) are deleted; their shared body becomes `resolve_announce_channel` in the
new module, with **zero callers in Phase 18** — it exists purely as a pre-built seam for Phase 19's
join-welcome (D-02). This is intentional dead-but-tested code, not a defect.

### Surfaces investigated and found NOT to need touching

| Surface | Why it's out of scope |
|---------|------------------------|
| `cogs/music.py::_get_text_channel` (line 1026-1039) | A **third**, unrelated fallback resolver — resolves the *last-active-music-channel* (`queue._text_channel_id`) for command-triggered posts: auto-lyrics thread posts, the idle-leave farewell ("Left the voice channel..."), and auto-queue announcements. It is never `DEXTER_CHANNEL_ID`-based and is NOT named by CONFIG-02/SC-3. These are responses to an active session a user started with `/play`, not unprompted ambient behavior in an untouched guild — CONFIG-04 does not apply. **Do not consolidate.** |
| `status_rotation` (bot.py:1052-1064) | **Not channel-bound at all.** It calls `bot.change_presence(activity=...)` — a bot-wide Discord *presence* (the "Playing ..." status text), not a message post to any guild channel. It has no channel resolver call site and needs no change for CONFIG-02. Confirmed by reading `_pick_next_status()` (bot.py:146-194) and the loop body (bot.py:1052-1064) — neither references `_resolve_dexter_channel`, `_get_ambient_channel`, or any channel object. |
| `ERROR_LOG_CHANNEL_ID` posts (`utils/logger.py::log_to_discord`, loop-error posts in `bot.py::_post_loop_error`) | Explicitly named in REQUIREMENTS.md as staying **global** — a private owner ops channel, not per-guild ambient content. Must NOT be folded into `guild_config`. No call site references `DEXTER_CHANNEL_ID` or either resolver. |
| Auto-lyrics posts, auto-queue posts | Route through `cogs/music.py::_get_text_channel` (see above) — command-session-scoped, not ambient. Out of scope. |
| Repeat-song roast, milestone roast | Traced through `cogs/music.py` and found to be delivered via the **same command-response channel** as the triggering `/play` (i.e., `_get_text_channel` or the interaction's own channel), not the ambient resolver. `grep -n "repeat_song\|milestone"` in `cogs/music.py` confirms these post inline in the active command flow, never via `_resolve_dexter_channel`/`_get_ambient_channel`. Not part of SC-3's 3 named sites and not touched by this phase. |

## Open Questions

1. **(RESOLVED) D-15's `GEMINI_API_KEY` concern.** Read every skipped live-DB test body
   (`test_database_phase11.py`, `test_database_phase15.py`, `test_database_phase16.py`,
   `test_memory.py`, `test_memory_taste.py`, `test_database_phase13.py`). **None construct a real
   `GeminiService` with a real key and none call `embed()` against the live network.** Every
   embedding used in a live-DB assertion is a synthetic literal:
   `embedding = [0.1] * config.EMBED_DIM` (or `0.2`/`0.3`/`0.4` in sibling tests) passed directly to
   `database.insert_memory`/`database.search_memories`. The one place `GeminiService` is
   instantiated in a test (`tests/test_memory.py:367`) uses `api_key="fake-key-for-test"` purely to
   assert on constructor attributes (`_embed_limiter is not _rate_limiter`), never to call the API.
   **CI can enable the pgvector service container with zero API secrets, exactly as D-15 assumes.**

2. **(RESOLVED — NEW FINDING, more consequential than Q1) Does `tests/conftest.py`'s `pool` fixture
   actually work against a real pgvector DB today?** No. The fixture
   (`tests/conftest.py:26-58`) does `p = await asyncpg.create_pool(dsn)` with **no `init=`
   parameter**, then `await init_db(p)`. Compare to `bot.py::_initialize_once` (lines 356-392),
   which (a) opens a *throwaway* connection and runs `CREATE EXTENSION IF NOT EXISTS vector;`
   **before** creating the real pool, specifically because pgvector's asyncpg codec
   (`pgvector.asyncpg.register_vector`) cannot register the `vector` type OID until the extension
   exists, and (b) passes `init=_register_vector` to `create_pool` so every pooled connection gets
   the codec. `tests/conftest.py` does neither. `database.insert_memory`/`search_memories` bind a
   plain `list[float]` as a query parameter against a `vector(768)` column — without the codec,
   asyncpg has no encoder for that type and the query will error (not skip) on a live pgvector DB.
   Confirmed 4 test files depend on this exact path with a real DB reachable:
   `test_database_phase11.py` (6 skipped tests, 2 of which — `test_insert_and_search_memories`,
   `test_bump_hit_and_surface` — call `insert_memory`/`search_memories` directly),
   `test_database_phase15.py` (`test_remember_forget_recall_empty`),
   `test_database_phase16.py` (`test_zero_memories_touched`). **Recommendation: Phase 18 must fix
   `tests/conftest.py`'s `pool` fixture (extension-first throwaway connection + `init=register_vector`
   on `create_pool`) as a prerequisite task before wiring the CI service container** — otherwise
   turning on `TEST_DATABASE_URL` in CI converts these ~9 currently-skipped tests into immediate,
   confusing CI failures on the very first green-gate run. This is squarely within CICD-01's scope
   (it's what makes the tests actually runnable, not just reachable) and should be called out
   explicitly as a task, not left implicit in "add a service container."

3. **(RESOLVED) Does the schema need `CREATE EXTENSION vector` to run against a
   `pgvector/pgvector:pg16` container, and does `init_db()` do it automatically?** Yes and yes —
   `database.py::SCHEMA_SQL` (line 68) has `CREATE EXTENSION IF NOT EXISTS vector;` as its literal
   first statement, executed as part of the single `conn.execute(SCHEMA_SQL)` call in `init_db`
   (line 201-207). The `pgvector/pgvector:pg16` Docker image ships the extension's shared library
   pre-installed in the image (confirmed via Docker Hub image listing — tags `pg16`, `0.8.x-pg16`,
   `pg16-bookworm` all exist), so `CREATE EXTENSION` only needs to activate it per-database, which
   `init_db()` already does unconditionally on every boot (idempotent `IF NOT EXISTS`). No schema
   change needed for CI to satisfy this — only the fixture-level codec-registration gap from Q2.

4. **(RESOLVED) Exact `TEST_DATABASE_URL` default + skip mechanism.** `tests/conftest.py:38-41`:
   `dsn = os.getenv("TEST_DATABASE_URL", "postgresql://dexter:dexter@localhost:5432/dexter_test")`.
   The `pool` fixture wraps `asyncpg.create_pool(dsn)` in `try/except Exception: pytest.skip(...)` —
   this is the primary skip mechanism for the ~107 tests that take a `pool` fixture argument
   (verified: `grep -c "async def test_.*(.*\bpool\b" tests/*.py` = 107, matching CONTEXT's "~108"
   almost exactly). A **separate**, additional `_SKIP_LIVE` module-level boolean
   (`_TEST_DSN == _LOCAL_DEFAULT`) exists only in the three newest Phase 11/15/16 files, as a
   fast pre-skip that avoids even attempting a connection during `--collect-only`. Both mechanisms
   key off the exact same env var and default DSN, so setting `TEST_DATABASE_URL` in CI to point at
   the service container unskips both categories simultaneously — no test-file changes needed for
   the skip logic itself (only the codec-registration fixture fix from Q2).

5. **(RESOLVED) Total live-DB test count and current suite size.** `pytest --collect-only -q`
   reports **956 tests collected**. This exactly equals the last-known-good baseline recorded in
   STATE.md at v1.3 close (848 pass + 108 skip = 956) — confirming no test count drift since
   2026-07-03. Of the 956, ~107 take the `pool` fixture (skip on connection failure today); 9 of
   those carry an additional `_SKIP_LIVE` decorator. Enabling the CI service container (with the
   Q2 fixture fix) should flip all ~107 from skip to pass, assuming the codec fix lands first.

## Standard Stack

### Core (no new runtime dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncpg | 0.31.0 (pinned, existing) | `guild_config` table I/O | Already the project's sole DB driver; no change |
| discord.py | ≥2.3.0 (existing) | `TextChannel`, `Guild`, permission checks in the resolver | Already the project's sole Discord library |
| pgvector | ≥0.3.6,<0.5 (existing) | Unaffected by this phase, but its `register_vector` codec is the fix target for the conftest gap (Q2) | Already a dependency; the fix reuses `pgvector.asyncpg.register_vector`, already imported in `bot.py` |

### Supporting (new dev-only tooling)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Ruff | 0.15.20 (verified installed/current at research time via `pip install ruff`; **not pinned to this exact patch in `pyproject.toml`** — pin a `>=` floor, e.g. `ruff>=0.15,<0.16`, so CI and local runs stay compatible without silently drifting to a future major) | Lint (replaces flake8+isort) + format check (replaces black) | CI job + optional pre-commit later |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Ruff (single tool) | flake8 + isort + black | Locked out by D-14 — two/three tools, two/three configs, slower CI; rejected explicitly in CONTEXT.md |
| `pgvector/pgvector:pg16` service container | A plain `postgres:16` container + manual `CREATE EXTENSION` install from source | The `pgvector/pgvector` image ships the extension pre-built; a plain postgres image would need an extra apt/build step in CI — unnecessary complexity for zero benefit |
| Boot seed inside `_initialize_once` | A separate one-off CLI script / migration tool | Rejected in CONTEXT.md D-08 — must be safe to re-run every boot forever, and must not require an operator to remember a manual step |

**Installation:**
```bash
pip install "ruff>=0.15,<0.16"
```
No `requirements.txt` change needed for runtime; add Ruff to a new `requirements-dev.txt` (does not
exist yet) or a `[project.optional-dependencies]` dev extra in the new `pyproject.toml` — planner's
discretion, either satisfies D-14/D-16.

**Version verification:** `ruff --version` → `ruff 0.15.20`, confirmed installed and runnable
locally at research time (2026-07-10) via a live `pip install ruff` + `ruff check`/`ruff format
--check` run against the actual repo (see Ruff Adoption Sizing below). This is a live, verified
result — not a training-data guess.

## Package Legitimacy Audit

Only one new package is introduced by this phase: **Ruff**, a dev-only lint/format tool (no
runtime import, never touches production data, no network calls at runtime). `slopcheck` was
attempted per protocol but installation was denied in this sandboxed research session (an
external-package-execution guard blocked it, unrelated to Ruff's own legitimacy). Per the
graceful-degradation rule, Ruff is tagged `[ASSUMED]` below despite being one of the most
widely-used Python tooling packages (Astral/Ruff is the de facto successor to flake8+black in the
Python ecosystem, written in Rust, millions of weekly PyPI downloads, actively maintained monorepo
at `github.com/astral-sh/ruff`) — the planner should still gate the actual `pip install ruff`
step behind a lightweight `checkpoint:human-verify` per the standing protocol, even though the
practical risk here is very low (dev-only tooling, not a runtime dependency, not handling secrets
or user data).

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| ruff | PyPI | ~4 years (first released 2022) | Tens of millions/week (widely known, not independently re-verified via slopcheck this session) | github.com/astral-sh/ruff | Unavailable (install blocked) | `[ASSUMED]` — Approved, planner gates the install step behind `checkpoint:human-verify` per protocol |

**Packages removed due to slopcheck `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** none.

*slopcheck was unavailable at research time (installation blocked by the sandbox's permission
system) — per protocol, Ruff is tagged `[ASSUMED]` and the planner must gate its install behind a
`checkpoint:human-verify` task.*

## Architecture Patterns

### System Architecture Diagram

```
                         ┌─────────────────────────────┐
                         │   bot.py :: on_ready         │
                         │   (_initialize_once, once)   │
                         └──────────────┬───────────────┘
                                        │
                     1. create asyncpg pool (existing)
                                        │
                     2. bot.guild_config = GuildConfigService(pool)   ◄── NEW
                                        │
                     3. await bot.guild_config.load_all()             ◄── NEW (D-06, fail-closed D-07)
                                        │            (SELECT * FROM guild_config, ONE round-trip)
                                        │
                     4. await bot.guild_config.seed_home_guild(       ◄── NEW (D-08/D-09)
                            guild_id=bot.get_channel(DEXTER_CHANNEL_ID).guild.id,
                            ambient_channel_id=DEXTER_CHANNEL_ID)
                                        │
                                (cogs load; unrelated to config)
                                        │
                                        ▼
        ┌───────────────────────────────────────────────────────────────┐
        │                     RUNTIME EVENT HANDLING                     │
        │                                                                 │
        │  on_voice_state_update / on_message / idle_check / startup     │
        │              │                                                  │
        │              ▼                                                  │
        │  bot.guild_config.resolve_ambient_channel(guild)   (D-01 strict)│
        │              │                                                  │
        │              ▼                                                  │
        │     self._cache.get(str(guild.id))   ◄── cache-only, NO db I/O  │
        │              │                                                  │
        │       miss → None (silent, D-06)                                │
        │       hit  → logic.guild_config.decide_ambient_channel(row)     │
        │              │                                                  │
        │              ▼                                                  │
        │      guild.get_channel(id) + permissions_for(guild.me)          │
        │              │                                                  │
        │      stale/unwritable → None + WARNING log (D-03, row untouched)│
        │      resolves        → TextChannel                              │
        └───────────────────────────────────────────────────────────────┘

        (Phase 19, NOT this phase)
        join-welcome / owner notice → bot.guild_config.resolve_announce_channel(guild)
                                       (the OLD 4-step fallback chain body, D-02)
```

### Recommended Project Structure

```
logic/
├── guild_config.py          # NEW — pure decide_ambient_channel + is_ambient_channel
services/
├── guild_config.py          # NEW — GuildConfigService: cache, both resolvers, DB I/O
models/
├── guild_config.py          # NEW (optional, Claude's discretion) — frozen GuildConfig dataclass
database.py                  # + guild_config DDL, load_all/seed helpers
bot.py                        # _initialize_once: wire service + load_all + seed; delete _resolve_dexter_channel
cogs/events.py                 # delete _get_ambient_channel; 6 call sites repoint
tests/
├── test_guild_config_logic.py   # NEW — mock-free lock for logic/guild_config.py
├── test_guild_config_service.py # NEW — GuildConfigService cache/resolver behavior
├── test_database_phase18.py     # NEW — schema + helper existence/shape (mirrors phase16 pattern)
├── conftest.py                  # FIX — register_vector + extension-first ordering in pool fixture
├── test_proactive_events.py     # UPDATE — lines 183/202 patch target changes
.github/
├── workflows/ci.yml         # NEW — pytest + ruff, pgvector service container
pyproject.toml                # NEW — [tool.ruff] config
```

### Pattern 1: Strict resolver as a structural safety property (D-01/D-05)

**What:** The ambient resolver returns `None` on any uncertainty (no row, unconfigured, stale
channel, missing permission) rather than falling back to a "best guess" channel.
**When to use:** Every unprompted/ambient Discord surface in this codebase, present and future.
**Example:**
```python
# services/guild_config.py — GuildConfigService.resolve_ambient_channel
def resolve_ambient_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
    row = self._cache.get(str(guild.id))
    channel_id = decide_ambient_channel(config_row=row)  # pure — logic/guild_config.py
    if channel_id is None:
        return None
    ch = guild.get_channel(channel_id)
    if ch is None or not isinstance(ch, discord.TextChannel):
        log.warning("guild_config: configured ambient channel %s in guild %s no longer resolves", channel_id, guild.id)
        return None
    if not ch.permissions_for(guild.me).send_messages:
        log.warning("guild_config: lost send_messages in configured channel %s (guild %s)", channel_id, guild.id)
        return None
    return ch
```

### Pattern 2: Pure decision function dispatched on, never re-derived (Phase 10 D-02 convention)

**What:** `logic/guild_config.py` contains zero I/O and zero Discord types; the service maps a
cache row (or its absence) to a plain `int | None`, and the caller (service method above) uses
that value directly — it does not re-check `config_row.get("configured")` itself.
**Example:**
```python
# logic/guild_config.py
from __future__ import annotations
from typing import Mapping


def decide_ambient_channel(*, config_row: Mapping | None) -> int | None:
    """D-01: pure decision. None (no row) or configured=False -> None (silence)."""
    if config_row is None:
        return None
    if not config_row.get("configured", False):
        return None
    channel_id = config_row.get("ambient_channel_id")
    return int(channel_id) if channel_id is not None else None


def is_ambient_channel(*, config_row: Mapping | None, channel_id: int) -> bool:
    """CONFIG-02: replaces the two bare-equality gates in events.py::on_message."""
    decided = decide_ambient_channel(config_row=config_row)
    return decided is not None and decided == channel_id
```

### Anti-Patterns to Avoid

- **A single `resolve_channel(guild, allow_fallback: bool)`:** rejected explicitly by D-02 — a
  boolean flag that flips a safety property is exactly the kind of parameter a future caller
  passes wrong. Two named functions, two names, two intents.
- **Re-deriving `configured`/floor logic in the cog:** violates the Phase 10 D-02 convention this
  codebase has enforced since Phase 10 — the glue dispatches on the pure function's return value,
  it does not re-implement the branch.
- **A lazy read-through cache (fetch on miss):** rejected by D-06 — the first ambient event per
  guild per boot would be exactly the live Neon round-trip CONFIG-03 forbids.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| pgvector codec registration | A custom `str(embedding)` → `'[0.1,0.2,...]'::vector` cast hack in test SQL | `pgvector.asyncpg.register_vector` (already a project dependency, already used correctly in `bot.py`) | The codec already exists and is proven correct in production; re-deriving a manual cast in the test fixture would diverge from the production path and risk a subtly different encoding |
| Boot re-entrancy guard for `AutoShardedBot`'s per-shard `on_ready` | A new guard specific to guild_config loading | The existing `_ready_done` / `_ready_initializing` module-level guard in `bot.py` (already covers ALL of `_initialize_once`, confirmed via official discord.py docs: "`on_ready` is not guaranteed to only be called once") | Adding the guild_config load/seed steps *inside* `_initialize_once` inherits this protection automatically — a parallel guard would be redundant and a maintenance burden |
| Lint/format tooling | flake8 + isort + black, three separate configs | Ruff, one tool, one `[tool.ruff]` table | D-14 locked; also objectively less config surface for a single-maintainer project |

**Key insight:** Every "don't hand-roll" in this phase is really "don't re-derive something the
codebase already got right once" — the pgvector codec, the on_ready guard, and the two-resolver
split are all precedents this phase should reuse or extend, not reinvent.

## Common Pitfalls

### Pitfall 1: CI pgvector service container ships green while 9 tests silently fail
**What goes wrong:** The team stands up the service container and env var per D-15 exactly as
described, expecting the ~108 skipped tests to unskip and pass. Instead, ~9 of them (the ones that
call `insert_memory`/`search_memories` with a live embedding) throw an asyncpg encoding error.
**Why it happens:** `tests/conftest.py`'s `pool` fixture never registers the pgvector codec and
never runs the extension-first throwaway-connection dance `bot.py` uses in production (see Open
Question 2).
**How to avoid:** Fix the `pool` fixture BEFORE wiring the CI workflow: extension-first connection,
then `asyncpg.create_pool(dsn, init=register_vector)`.
**Warning signs:** Any local run with a real `TEST_DATABASE_URL` pointed at a pgvector DB producing
`asyncpg.exceptions.DataError` or similar on `insert_memory` calls.

### Pitfall 2: Conflating the ambient resolver with the announce resolver
**What goes wrong:** A future contributor (or the executor of THIS phase) is tempted to give
`resolve_ambient_channel` a `fallback=True` escape hatch "just for the startup message, since it's
kind of a system notice."
**Why it happens:** The startup message *feels* like an announcement, but CONFIG-04 explicitly
lists it as an ambient surface that must go silent in an unconfigured guild.
**How to avoid:** Treat the Call-Site Inventory above as authoritative — all 6 current call sites
are ambient. `resolve_announce_channel` has ZERO callers in Phase 18; that is correct and expected,
not a sign something was missed.
**Warning signs:** Any call to `resolve_announce_channel` appearing in this phase's diff.

### Pitfall 3: Treating `cogs/music.py::_get_text_channel` as a fourth site to consolidate
**What goes wrong:** A broad grep for "channel resolver" turns up `_get_text_channel` and an
overzealous refactor folds it into the new seam too, breaking auto-lyrics/idle-farewell/auto-queue
posts in guilds that never configured an ambient channel but ARE actively playing music.
**Why it happens:** It has a similar 3-step permission-checking shape to the two functions actually
named by SC-3.
**How to avoid:** SC-3 names exactly `bot.py::_resolve_dexter_channel`,
`cogs/events.py::_get_ambient_channel`, and the two bare-equality gates. `_get_text_channel` is not
on that list and its behavior (post where the user last ran `/play`) has nothing to do with
`DEXTER_CHANNEL_ID` or the new `guild_config` table.
**Warning signs:** A diff touching `cogs/music.py::_get_text_channel`.

### Pitfall 4: `AutoShardedBot` re-entrancy on the guild_config boot steps
**What goes wrong:** A dev adds the cache-load + seed calls as a fresh top-level `@bot.event
async def on_ready()` handler (a second one) instead of inside `_initialize_once`, and each shard's
READY event re-runs the seed (harmless, since `ON CONFLICT DO NOTHING` — but the cache-reload IS
wasted work and, if it ever became a write, would be unsafe).
**Why it happens:** It's tempting to add "one clean new on_ready block" rather than extend the
existing monolithic `_initialize_once`.
**How to avoid:** Add both steps inside the existing `_initialize_once` function, after pool
creation. This function only runs once thanks to the `_ready_done`/`_ready_initializing` guard
already wrapping it (confirmed via official discord.py docs — `on_ready` fires per-shard/per-
reconnect, and this codebase already solved that problem once).
**Warning signs:** A second `@bot.event async def on_ready()` definition anywhere in the diff.

### Pitfall 5: `bot.get_channel()` returning `None` at seed time
**What goes wrong:** The home-guild seed calls `bot.get_channel(config.DEXTER_CHANNEL_ID)` too
early (e.g., in `setup_hook`, which fires BEFORE the gateway populates guild/channel caches) and
gets `None`, silently skipping the seed on every boot.
**Why it happens:** `setup_hook` runs once before `on_ready`/before the guild cache is filled;
`bot.get_channel` depends on that cache.
**How to avoid:** Run the seed step inside `_initialize_once` (called from `on_ready`, after the
gateway has populated `bot.guilds`), never inside `setup_hook`. D-10 already covers the "genuinely
unset/unresolvable" case as an expected silent INFO skip — that is different from "ran too early
and always fails."
**Warning signs:** The seed step consistently no-ops even when `DEXTER_CHANNEL_ID` is set and valid
in `.env`.

### Pitfall 6: Ruff format collapsing the atomic-commit discipline (D-16)
**What goes wrong:** `ruff format .` (no `--check`) is run as part of the SAME commit as the
config-seam refactor, producing a diff that's impossible to review (refactor logic buried in
whitespace/quote-style churn across 73 files).
**Why it happens:** It's one command; it's tempting to just run it once and move on.
**How to avoid:** Run the full-repo `ruff format` (and `ruff check --fix`) as its OWN commit,
BEFORE or clearly separated from the `guild_config`/CI code changes, per D-16's explicit
instruction. The CI workflow itself can land in the same commit as the lint cleanup, or before it —
either way, the config-seam refactor must not be entangled with 73 files of formatting diff.
**Warning signs:** A single commit touching both `services/guild_config.py` and, say,
`utils/logger.py`'s formatting.

### Pitfall 7: Native-extension dev dependencies failing on a fresh CI runner
**What goes wrong:** `pip install -r requirements.txt` fails or hangs on `ubuntu-latest` because
`PyNaCl` or `davey` (Discord voice E2E encryption) need a native build toolchain not present on the
runner.
**Why it happens:** Both are native-extension packages; PyNaCl bundles a static libsodium in its
manylinux wheels (should "just work"), but `davey` (a newer, smaller PyPI package, currently at
0.1.6, only 0.1.5 pinned locally) has less track record for prebuilt Linux wheels.
**How to avoid:** The FIRST CI run is the actual verification — budget for a possible
`apt-get install build-essential libsodium-dev` fallback step if `pip install` fails on `davey`.
This is a MEDIUM-confidence risk (not verified against a real Linux runner in this research
session — no live GitHub Actions run was executed) — flag for the planner to watch on first CI run,
not a blocker to plan around preemptively with speculative apt-get steps.
**Warning signs:** `pip install` step in the very first CI run failing with a compiler-not-found
error on `davey` or `PyNaCl`.

## Code Examples

### `guild_config` DDL (mirrors `guild_jams`, database.py:188-197)

```sql
-- Phase 18: per-guild ambient config seam (CONFIG-01). guild_id is TEXT to match
-- every other guild-keyed table's convention (guild_jams, guild_queues) — Discord
-- snowflakes stored as TEXT throughout this codebase, never BIGINT.
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id            TEXT PRIMARY KEY,
    ambient_channel_id  TEXT,
    configured          BOOLEAN NOT NULL DEFAULT false,
    silenced            BOOLEAN NOT NULL DEFAULT false,   -- Phase 20 reader only (D-11)
    is_blocked          BOOLEAN NOT NULL DEFAULT false,   -- Phase 20 reader only (D-11)
    joined_at           TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);
```
No index needed beyond the primary key — the only query pattern is `SELECT *` (load-all-at-boot,
D-06) and single-row upserts by `guild_id`, both served by the PK.

### `database.py` helpers (mirror `get_proactive_opt_out`/`set_proactive_opt_out`, lines 318-376)

```python
async def load_all_guild_configs(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    """D-06: ONE SELECT * at boot. Never called again in the hot path."""
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT guild_id, ambient_channel_id, configured, silenced,"
            "       is_blocked, joined_at, updated_at"
            " FROM guild_config"
        )


async def seed_guild_config_if_absent(
    pool: asyncpg.Pool, *, guild_id: str, ambient_channel_id: str
) -> asyncpg.Record | None:
    """D-08/D-09: idempotent home-guild seed. ON CONFLICT DO NOTHING — the env
    var is bootstrap-only and never overwrites an existing row (D-09). Returns
    the current row (freshly inserted OR pre-existing) so the caller can
    refresh exactly that one cache entry; returns None only if the row
    somehow still can't be read back (should not happen under normal operation).
    """
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO guild_config (guild_id, ambient_channel_id, configured)"
            " VALUES ($1, $2, true)"
            " ON CONFLICT (guild_id) DO NOTHING",
            guild_id, ambient_channel_id,
        )
        return await conn.fetchrow(
            "SELECT guild_id, ambient_channel_id, configured, silenced,"
            "       is_blocked, joined_at, updated_at"
            " FROM guild_config WHERE guild_id = $1",
            guild_id,
        )
```

### `tests/conftest.py` fix (Open Question 2 — REQUIRED before CI wiring)

```python
# Source: mirrors bot.py::_initialize_once's extension-first pattern (lines 356-392)
from pgvector.asyncpg import register_vector

@pytest_asyncio.fixture
async def pool():
    dsn = os.getenv("TEST_DATABASE_URL", "postgresql://dexter:dexter@localhost:5432/dexter_test")
    try:
        # Extension-first: a throwaway connection ensures `vector` exists
        # BEFORE the real pool's init= callback tries to register its codec.
        _ext_conn = await asyncpg.connect(dsn=dsn)
        try:
            await _ext_conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        finally:
            await _ext_conn.close()

        p = await asyncpg.create_pool(dsn, init=register_vector)
    except Exception as exc:
        pytest.skip(f"Postgres unavailable ({exc}); skipping live-DB test")
        return
    await init_db(p)
    yield p
    async with p.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS guild_queues, song_history,"
            " user_artist_counts, image_generation_log,"
            " bot_daily_stats, user_profiles,"
            " user_favorites, user_playlists,"
            " resolution_cache, guild_jams, guild_config,"
            " user_memories CASCADE"
        )
    await p.close()
```
(Note: the existing teardown DROP list is also missing `user_memories` and `guild_config` — both
should be added while this fixture is being touched, though this is a pre-existing gap unrelated to
Phase 18's own table and not itself a blocker; each test creates its own uniquely-prefixed
`user_id` values so cross-test pollution hasn't surfaced as a symptom yet, but a CASCADE DROP is
cheap correctness insurance.)

### Ruff config (`pyproject.toml`, new file)

```toml
[tool.ruff]
target-version = "py311"   # matches CLAUDE.md's "Python 3.11+" floor
line-length = 120           # verified via live run: line-length=88 (default) produces 902
                             # E501 findings alone; 120 drops that to 32 genuine long lines,
                             # a realistic near-default starting ruleset per D-14

[tool.ruff.lint]
select = ["E", "F", "W", "I"]   # pyflakes + pycodestyle + isort — near-default, D-14
ignore = []

[tool.ruff.lint.per-file-ignores]
"tests/*.py" = ["F401"]   # test files sometimes import fixtures/mocks only for side effects

[tool.ruff.format]
# defaults are fine — black-compatible formatting
```

### GitHub Actions workflow (`.github/workflows/ci.yml`, new file)

```yaml
name: CI

on:
  push:
  pull_request:

permissions:
  contents: read   # least-privilege — this workflow only reads code and runs tests/lint

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: dexter
          POSTGRES_PASSWORD: dexter
          POSTGRES_DB: dexter_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    env:
      TEST_DATABASE_URL: postgresql://dexter:dexter@localhost:5432/dexter_test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"
      - run: pip install -r requirements.txt
      - run: pip install "ruff>=0.15,<0.16"
      - run: ruff check .
      - run: ruff format --check .
      - run: pytest -q
```
(A single combined job is proposed — lint and test are both fast enough that splitting into two
parallel jobs is optional polish, not a requirement; planner's discretion per CONTEXT.md.)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Hardcoded single `config.DEXTER_CHANNEL_ID` + 4-step fallback chain, duplicated in `bot.py` and `cogs/events.py` | Strict per-guild `guild_config` row via a single cached service, plus a separate named `resolve_announce_channel` for the (rare) legitimate fallback use case | This phase | Multi-tenant safety becomes structural, not a "remembered convention"; a stray guild that never ran `/setup` gets zero unprompted output |
| No CI | GitHub Actions on every push/PR: pytest + Ruff, both blocking | This phase | Every phase from 19 onward (especially Phase 21's memory-scoping surgery) executes behind a green gate instead of relying on local-only `pytest` runs |

**Deprecated/outdated:**
- The 4-step ambient fallback chain (env → last-active-music-channel → system-channel →
  first-writable) is deprecated as an *ambient* resolution strategy — it survives only as
  `resolve_announce_channel`, explicitly scoped to join-welcome/owner-notice use in Phase 19.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Ruff is a legitimate, safe-to-install PyPI package (slopcheck unavailable this session) | Package Legitimacy Audit, Standard Stack | Extremely low in practice (Ruff is one of the most widely-adopted Python dev tools), but per protocol still flagged `[ASSUMED]` — gate the install behind `checkpoint:human-verify` |
| A2 | `davey`/`PyNaCl` will install cleanly on a fresh `ubuntu-latest` GitHub Actions runner without extra native build steps | Common Pitfalls (Pitfall 7) | If wrong, the very first CI run fails at the `pip install` step; low-cost to detect (first run) and fix (add an `apt-get` step), not a design-level risk |
| A3 | A single combined lint+test CI job (vs. two parallel jobs) is an acceptable structure | Code Examples (workflow YAML) | Purely a speed/parallelism tradeoff, not a correctness risk — planner's discretion per CONTEXT.md, easy to split later |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Everything | ✓ | 3.12.x locally (project floor is 3.11+ per CLAUDE.md) | CI pins 3.11 explicitly to match the documented floor |
| asyncpg | `guild_config` I/O | ✓ (existing dependency) | 0.31.0 | — |
| Docker | Local pgvector testing (optional, not required for CI) | ✓ (installed) but daemon not running in this sandbox | 29.5.3 client | Not required — CI provides its own Postgres via GitHub-hosted service containers, independent of local Docker |
| Ruff | Lint/format gate | ✓ (installed for research verification) | 0.15.20 | — |
| pgvector/pgvector:pg16 (Docker image) | CI service container | Not verified by an actual container pull in this session (Docker daemon unavailable) — verified only via Docker Hub tag listing | pg16 tag confirmed to exist | If the tag were ever retired, `pgvector/pgvector:pg16-bookworm` or a pinned `0.8.x-pg16` tag are documented alternatives |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** pgvector container image verified via registry listing
only, not a live pull in this sandbox (Docker daemon not running) — the planner should treat the
very first CI run as the actual verification of this dependency, per Pitfall 7's spirit.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.4.0 (strict mode via explicit `@pytest.mark.asyncio` on every async test — confirmed, no `asyncio_mode` config needed) |
| Config file | None today (no `pytest.ini`/`setup.cfg`) — Phase 18 does not need to add one; Ruff's config lives in the new `pyproject.toml`, which is separate from pytest config |
| Quick run command | `pytest -q -k "guild_config or health"` (new logic/service tests are fast, no DB needed) |
| Full suite command | `pytest -q` (956 tests today: 848 pass / 108 skip / 0 fail per the last verified baseline; with the CI pgvector container + conftest fix, the skip count should drop toward 0 for the ~107 pool-fixture tests) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|-------------|
| CONFIG-01 | `guild_config` table exists with all 7 columns | unit (schema introspection, mirrors `test_database_phase16.py`'s pattern) | `pytest tests/test_database_phase18.py -x` | ❌ Wave 0 |
| CONFIG-02 | `decide_ambient_channel`/`is_ambient_channel` replace the fallback chain + bare-equality gates; old functions gone | unit (mock-free pure logic) + structural (`inspect.getsource` grep for `DEXTER_CHANNEL_ID` absence in `cogs/`, mirrors `test_proactive_events.py::test_accuracy_firewall`'s style) | `pytest tests/test_guild_config_logic.py -x` | ❌ Wave 0 |
| CONFIG-03 | `GuildConfigService` cache-only reads, no DB round-trip on miss | unit (service test with a spy/mock pool asserting zero `.acquire()` calls after `load_all()`) | `pytest tests/test_guild_config_service.py -x` | ❌ Wave 0 |
| CONFIG-04 | Unconfigured guild → all ambient surfaces silent | unit (each of the 6 call sites, mirrors `test_proactive_events.py`'s `_make_bot`/`_make_message` pattern) | `pytest tests/test_proactive_events.py tests/test_vision_events.py tests/test_ambient_recall_cadence.py -x` | ✅ (existing files, need updates) |
| CONFIG-05 | Home guild seed idempotent, `ON CONFLICT DO NOTHING` | unit (live-DB, mirrors `test_database_phase16.py::test_opt_out_roundtrip`'s round-trip style) + structural (`inspect.getsource` assert on `ON CONFLICT (guild_id) DO NOTHING` text) | `pytest tests/test_database_phase18.py -x` (live-DB portion needs `TEST_DATABASE_URL`) | ❌ Wave 0 |
| CICD-01 | pytest + Ruff both run and block on push/PR | manual-only (cannot be asserted from within the test suite itself — first real push/PR IS the verification) | N/A — verify via GitHub Actions run history after first push | N/A |

### Sampling Rate
- **Per task commit:** `pytest -q -k "guild_config"` (fast, no live DB required for the pure-logic
  and mocked-service tests)
- **Per wave merge:** `pytest -q` full suite (still fast locally without `TEST_DATABASE_URL` set —
  the ~107 live-DB tests continue to skip until a developer opts in locally)
- **Phase gate:** Full suite green locally before `/gsd-verify-work`; the CI workflow itself is only
  verifiable by an actual push (the workflow YAML's correctness cannot be unit-tested)

### Wave 0 Gaps
- [ ] `tests/test_database_phase18.py` — covers CONFIG-01/CONFIG-05
- [ ] `tests/test_guild_config_logic.py` — covers CONFIG-02 (pure logic)
- [ ] `tests/test_guild_config_service.py` — covers CONFIG-03
- [ ] `tests/conftest.py` fix (register_vector + extension-first ordering) — prerequisite for
  CICD-01's live-DB tests to pass rather than error once CI is wired (Open Question 2)
- [ ] `pyproject.toml` `[tool.ruff]` — new file, no existing config to extend
- [ ] `.github/workflows/ci.yml` — new file, no existing workflow to extend

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | This phase has no new auth surface — no new commands, no new user-facing input |
| V3 Session Management | No | N/A |
| V4 Access Control | Yes (narrowly) | The home-guild seed derives `guild_id` from `bot.get_channel(DEXTER_CHANNEL_ID)` — a config value, not user input; no access-control decision is made by this phase's code (Phase 20 owns `is_blocked`/`silenced` enforcement) |
| V5 Input Validation | Yes | All `guild_config` writes are `$N`-parameterized asyncpg calls (mirrors every existing helper in `database.py`) — no string interpolation anywhere in the proposed DDL/helpers |
| V6 Cryptography | No | N/A — no secrets, tokens, or crypto touched by this phase |

### Known Threat Patterns for this phase's stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| SQL injection via `guild_id`/`ambient_channel_id` | Tampering | All `guild_config` reads/writes use `$N` positional asyncpg parameters, matching every existing table helper in `database.py` — no f-string SQL anywhere in this phase's proposed code |
| Cross-guild config/data leakage (a guild reading/affecting another guild's `ambient_channel_id`) | Information Disclosure / Tampering | Every helper is scoped by `guild_id` in its `WHERE`/`VALUES` clause; the in-memory cache is keyed by `guild_id` string, `get()` never accepts a second guild's id implicitly (mirrors the `user_id`-scoping discipline already proven in `services/memory.py`) |
| GitHub Actions supply-chain: a malicious PR triggering the workflow with elevated permissions or secret access | Elevation of Privilege | Use `pull_request` (not `pull_request_target`) — the proposed workflow runs on the PR's own code with the PR author's own permissions, no repo secrets are referenced anywhere in the workflow, and top-level `permissions: contents: read` denies write access even to the default `GITHUB_TOKEN` |
| Stale `configured=true` row masking a genuinely broken config after a permission change | Denial of Service (soft — ambient goes silent, not a crash) | Intentional per D-03 — a transient permission blip must not permanently un-configure a guild; the log line (not a Discord-visible message) is the detection mechanism, consistent with the "boring Dexter over broken Dexter" philosophy already established in Phase 16/17 |
| CI service-container credentials (`POSTGRES_PASSWORD: dexter`) | Information Disclosure | Ephemeral, network-isolated to the single CI job, torn down after the run, never touches production Neon credentials or the real `DATABASE_URL` secret — zero overlap with production secrets by construction (D-15's "zero secrets" design) |

## Sources

### Primary (HIGH confidence — direct repo reads, verified line numbers)

- `bot.py` (full file read, 2026-07-10) — `_resolve_dexter_channel` (103-143), `_initialize_once`
  (356-502), `_post_startup_messages` (505-522), `idle_check` (674-747), `_ready_done` guard
  (307-341)
- `cogs/events.py` (full file read) — `_get_ambient_channel` (98-137), all 6 ambient call sites,
  `on_message` gates (443-460)
- `database.py` (full file read) — `SCHEMA_SQL`, `guild_jams`/`resolution_cache` DDL,
  `get_proactive_opt_out`/`set_proactive_opt_out` pattern, asyncpg multi-statement DDL confirmed
  (`init_db`, lines 201-207)
- `config.py` (full file read) — `DEXTER_CHANNEL_ID` (line 57), all Phase 11-17 config precedent
- `tests/conftest.py` (full file read) — the `pool` fixture gap (Open Question 2)
- `tests/test_proactive_events.py` (full file read) — exact patch lines confirmed (183, 202)
- `tests/test_database_phase11.py`, `test_database_phase15.py`, `test_database_phase16.py`,
  `test_memory.py` (relevant sections read) — confirmed no live `GEMINI_API_KEY` usage anywhere
- `logic/proactive.py`, `logic/vision.py` (full files read) — pure-gate seam template
- `logic/health.py`, `cogs/ops.py` (relevant sections) — confirmed `/health` unaffected by this phase
- `services/memory.py`, `services/metrics.py`, `services/queue_persistence.py` (relevant sections)
  — service-wiring convention template
- `models/memory.py` (relevant section) — frozen-dataclass convention template
- `.planning/codebase/TESTING.md` — testing convention (pure logic TDD, Discord glue untested-by-design)
- Live local command runs (this session): `ruff check . --select E,F,W,I --statistics` (both at
  default 88 and at 120 line-length), `ruff format --check .`, `pytest --collect-only -q`,
  `git ls-files "*.py" | wc -l` / `xargs wc -l`, `pip show`/`pip index versions` for ruff/davey/PyNaCl

### Secondary (MEDIUM confidence — official docs via Context7, cross-verified)

- Context7 `/rapptz/discord.py` — `on_ready` "not guaranteed to only be called once," fires per
  shard/reconnect (confirms the existing `_ready_done` guard's own rationale)
- WebSearch (verified against multiple independent sources: Simon Willison's TILs, GitHub Docs,
  DEV Community) — GitHub Actions Postgres service container pattern with `health-cmd pg_isready`
- WebSearch (Docker Hub tag listing) — `pgvector/pgvector:pg16` tag confirmed to exist; not pulled
  live in this session (Docker daemon unavailable in sandbox)

### Tertiary (LOW confidence — flagged for validation)

- `davey`/PyNaCl CI-runner compatibility (Pitfall 7, Assumption A2) — not verified against an actual
  Linux CI run this session; flagged as a first-run risk, not a design blocker

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new runtime deps; Ruff verified installed/runnable locally against the
  actual repo
- Architecture: HIGH — every file/line claim re-verified against the current repo, not trusted from
  CONTEXT.md
- Pitfalls: HIGH for Pitfalls 1-6 (all verified via direct code read or live command run); MEDIUM
  for Pitfall 7 (native-extension CI compatibility, not verified against a live Linux runner)

**Research date:** 2026-07-10
**Valid until:** 30 days (stable domain — no fast-moving external API surface; the one time-boxed
risk is Ruff's own rule/version drift, mitigated by pinning `ruff>=0.15,<0.16` rather than floating)
