# Phase 18: Per-Guild Config Foundation & CI Gate - Context

**Gathered:** 2026-07-10
**Status:** Ready for planning

> **Session note:** Unlike Phases 14–17 (where decisions were adopted on the user's behalf
> during AFK windows), **every decision below was explicitly selected by the user** across five
> AskUserQuestion rounds covering four chosen gray areas plus a fifth (forward-column semantics)
> the user asked to open. All numeric/structural minutiae remain planner discretion per the
> Phase 11/13/14/15/16/17 precedent.

<domain>
## Phase Boundary

Phase 18 replaces Dexter's hardcoded single-channel assumption (`config.DEXTER_CHANNEL_ID`) with
a **real per-guild configuration seam** — a `guild_config` table, a cached `GuildConfigService`,
and **one** consolidated ambient-channel resolver — and stands up a **green CI gate** that every
subsequent v1.4 phase (especially Phase 21's surgery on the scarred memory subsystem) executes
behind.

This is a **seam, not a feature**. Phase 18 ships no user-facing command. Its success is proven
by two observable facts: the owner's home guild behaves exactly as before, and every other guild
is completely ambient-silent.

**In scope:**
- A `guild_config` table in `SCHEMA_SQL` following the `guild_jams` / `resolution_cache` idiom
  (CONFIG-01), including the forward columns `silenced` + `is_blocked` that only Phase 20 reads.
- A `GuildConfigService` (`services/guild_config.py`) serving per-guild config from an in-memory
  cache loaded once at boot, push-invalidated on write — never a per-event Neon round-trip
  (CONFIG-03).
- A pure `logic/guild_config.py` decision seam (Phase 10 convention), mock-free tested.
- **Consolidation (CONFIG-02):** `bot.py::_resolve_dexter_channel` and
  `cogs/events.py::_get_ambient_channel` collapse into the service; the two bare-equality
  `message.channel.id == config.DEXTER_CHANNEL_ID` gates at `cogs/events.py:445-446` and
  `455-457` route through the same predicate.
- **Ambient default-OFF (CONFIG-04):** every ambient/unprompted surface (voice roasts, proactive
  callbacks, vision roasts, idle-loneliness, startup message, status-rotation posts) stays silent
  in a guild with no config row. Core commands (`/play`, `/ask`, `/imagine`, …) work immediately
  on join.
- **Home-guild seed (CONFIG-05):** an idempotent boot seed derives the home guild from
  `config.DEXTER_CHANNEL_ID` so nothing changes for the owner.
- **CI gate (CICD-01):** GitHub Actions on every push + PR — pytest (with a pgvector service
  container) + Ruff lint/format check, both blocking.

**Out of scope (belongs to later phases):**
- `/setup` and the channel dropdown picker → Phase 19 (ONBOARD-02/03). **No stopgap owner-only
  setter ships in Phase 18** (D-11).
- Per-guild `ambient_roasts_enabled` / `vision_roasts_enabled` toggle columns → Phase 19 ALTERs
  them in (D-10).
- Any *reader* of `silenced` / `is_blocked`, the owner control plane, and
  `CommandTree.interaction_check` block enforcement → Phase 20 (D-09).
- `on_guild_join` / `on_guild_remove` lifecycle handlers → Phase 19/20/21.
- Memory guild-scoping → Phase 21. The README build badge → Phase 23 (D-08).
- Any change to `OWNER_ID` / `ERROR_LOG_CHANNEL_ID` — these stay **global** (owner identity +
  private cross-guild ops channel) and must NOT be folded into `guild_config`.

</domain>

<decisions>
## Implementation Decisions

### Ambient channel resolution & the fallback chain (CONFIG-02 / CONFIG-04)

- **D-01 (user-selected): ambient resolution is STRICT — the config row or silence.** Ambient
  surfaces resolve **only** `guild_config.ambient_channel_id`. No row, or a row whose channel
  no longer resolves → return `None` → the surface stays silent. The existing four-step fallback
  chain (env channel → last active music channel → `guild.system_channel` → first writable text
  channel) is **removed from the ambient path entirely**. This makes CONFIG-04's
  "silent until `/setup`" a *structural property* of the resolver rather than a behavior each
  caller must remember to check.
  *(Rejected: keeping the music-channel step — an unconfigured guild would get ambient output the
  moment someone ran `/play`; keeping the full chain — directly contradicts the locked
  "ambient default-OFF until `/setup`" milestone decision.)*

- **D-02 (user-selected): the fallback chain survives as a SECOND, explicitly-named resolver for
  the announce path.** Two named functions in the same module, two explicit intents:
  - `resolve_ambient_channel(guild) -> TextChannel | None` — strict, row-only (D-01). Used by
    every unprompted/ambient surface.
  - `resolve_announce_channel(guild) -> TextChannel | None` — the preserved best-effort
    fallback chain. Used **only** by join-welcome (Phase 19 / ONBOARD-01) and owner-facing
    notices. Never by an ambient surface.

  CONFIG-02's "exactly one code path" holds **per intent** — there is one ambient resolver and
  one announce resolver, and the duplicated `bot.py` / `events.py` copies are both gone. Phase 19
  inherits a pre-built seam.
  *(Rejected: delete-now-rebuild-in-19 — the chain logic gets re-derived and re-reviewed a phase
  later; a single `resolve_channel(guild, allow_fallback: bool)` — a boolean that flips a safety
  property is exactly the argument a future caller passes wrong.)*

- **D-03 (user-selected): a stale/unwritable configured channel is a SILENT SKIP with a log
  line.** If `ambient_channel_id` names a deleted channel, or one where Dexter has lost
  `send_messages`, the resolver returns `None`, the surface stays quiet, and a `WARNING` lands in
  `dexter.log`. **The row is left intact and `configured` stays `true`** — re-creating the channel
  or re-granting permission just works. Mirrors the Phase 17 "no output beats a wrong output"
  silent-skip instinct.
  *(Rejected: auto-clearing `configured` — a transient permission blip would permanently
  un-configure a guild; falling back to the chain "just this once" — an admin who designated
  `#bot-spam` did not consent to `#general`.)*

### Config seam shape, cache, and failure mode (CONFIG-03)

- **D-04 (user-selected): the seam is `services/guild_config.py::GuildConfigService`**, wired in
  `bot.py` and attached as a bot attribute exactly like `memory_service` / `metrics`. Cogs reach
  it via `self.bot.guild_config`. It owns the cache, the `database.py` helper call sites, and
  both resolver functions (D-02). Matches the established cog → service → model layering and
  gives Phases 19–21 one obvious extension point for the push-invalidate call that `/setup`
  (Phase 19) and the kill-switch (Phase 20) both need.
  *(Rejected: `utils/channels.py` + a module-global dict — no obvious owner for invalidation,
  harder to test; methods on the `Bot` subclass — grows `bot.py` and makes `events.py` reach
  through `self.bot` into playback-adjacent code, the exact duplication CONFIG-02 exists to kill.)*

- **D-05 (user-selected): extract a pure `logic/guild_config.py` decision seam** — keyword-only,
  `discord`-free, `datetime`-free functions the service dispatches on (e.g. a
  `decide_ambient_channel(*, config_row, ...) -> int | None` and the
  is-this-the-ambient-channel predicate that replaces the two bare-equality gates). The service
  does I/O; the pure function decides. Locks the silent-until-configured invariant under mock-free
  tests, the same treatment `logic/vision.py` and `logic/proactive.py` received. Per the standing
  D-02-of-Phase-10 rule, the glue **dispatches on the returned value and does not mirror the
  branch logic back in the caller**.
  *(Rejected: service methods tested with a stubbed row — breaks a convention that has caught real
  scars, Phase 13 CR-01 and Phase 16 WR-03 among them.)*

- **D-06 (user-selected): load-all at boot; a cache MISS is authoritative.** One
  `SELECT * FROM guild_config` at boot fills the dict. A miss means *that guild has no config* →
  silent, **no DB read, no round-trip** — satisfying CONFIG-03 literally. Phase 19's
  `on_guild_join` will insert the row and populate the cache in the same step; `/setup` and the
  Phase 20 kill-switch push-invalidate on write.
  *(Rejected: lazy read-through — the first ambient event per guild per boot IS a Neon round-trip,
  the thing CONFIG-03 forbids; preload + lazy fill — a live-DB path in the hot event handler that
  almost never executes and therefore never gets exercised.)*

- **D-07 (user-selected): FAIL CLOSED.** If the boot load fails or a config write throws (Neon
  scale-to-zero, timeout), an unpopulated/errored cache means **every guild reads as
  unconfigured**: ambient surfaces go quiet; core commands (`/play`, `/ask`) keep working. The
  error surfaces to `dexter.log` + `ERROR_LOG_CHANNEL_ID`. Worst case is a boring Dexter, never a
  Dexter roasting a server that never opted in.
  *(Rejected: fail-open to the env channel — a bug in the load path would silently restore the
  pre-refactor single-channel world and hide the failure; fail-closed + bounded retry loop — more
  moving parts for a failure mode a restart already fixes.)*

### Home-guild seeding (CONFIG-05)

- **D-08 (user-selected): an idempotent one-time boot seed.** `config.DEXTER_CHANNEL_ID` is a
  *channel* id and `guild_config` is keyed by *guild* id, so at boot (after the cache load)
  resolve `bot.get_channel(DEXTER_CHANNEL_ID)` → `ch.guild.id`, then
  `INSERT ... ON CONFLICT (guild_id) DO NOTHING` with `configured = true`, and refresh that cache
  entry. The home guild becomes an **ordinary tenant with an ordinary row** — `/setup`, silence,
  force-leave, and the Phase 21 MEM-04 purge all treat it identically. Safe to re-run on every
  boot, forever.
  *(Rejected: a resolver-level env fallback with no row — makes the home guild a permanent special
  case inside the one function every ambient surface calls, and Phase 19/20/21 each have to reason
  about a guild with no row; manual `/setup` after deploy — breaks CONFIG-05's explicit "current
  behavior is unchanged after the refactor" promise for one restart window.)*

- **D-09 (user-selected): `ON CONFLICT DO NOTHING`, never `DO UPDATE` — the env var is a
  bootstrap value with no ongoing authority.** Once the row exists it wins forever: a later
  `/setup` change survives the next restart, and deleting `DEXTER_CHANNEL_ID` from `.env` changes
  nothing for an already-seeded guild. This is precisely what CONFIG-05 asks of the env var, and
  it stops a stale `.env` from silently overriding a deliberate `/setup`.
  *(Rejected: `DO UPDATE` — every boot re-asserts the env value, making `/setup` a silently
  self-reverting no-op in the home guild.)*

- **D-10 (user-selected): an unset or unresolvable `DEXTER_CHANNEL_ID` is skipped silently at
  INFO — not an error.** No row seeded → no guild configured → Dexter is ambient-silent
  everywhere until someone runs `/setup`. This is the **correct and desirable** state for a fresh
  clone of the repo (a recruiter running it), and for CI, where the env var is absent.
  *(Rejected: warn to the error channel — cries wolf on every fresh deploy where an unset value is
  entirely intentional; refuse to boot — directly hostile to the milestone goal, since an invitable
  bot must run fine with no home guild at all.)*

### Forward-column semantics (schema ownership across phases)

- **D-11 (user-selected): create `silenced` + `is_blocked` now; read them in NO Phase 18 code.**
  CONFIG-01 names them explicitly, so ship the full column set with sane `false` defaults. Phase
  18 writes no reader; **Phase 20 adds the readers**, the setters, and the tests together.
  *(Rejected: wiring `is_blocked` into the resolver now "so OWNER-05's single seam is already
  true" — that ships a kill-switch enforcement path with no way to set the flag and no test of the
  owner flow: dead code that looks live; shipping only the columns Phase 18 reads — contradicts
  CONFIG-01's literal column list.)*

- **D-12 (user-selected): ONBOARD-04's toggles are Phase 19's to add.** Phase 18 ships **exactly**
  CONFIG-01's columns. Phase 19 adds `ambient_roasts_enabled` / `vision_roasts_enabled` via
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` — the same idiom that added
  `bot_daily_stats.total_errors` (Phase 8) and `user_profiles.proactive_opt_out` (Phase 16). Each
  phase owns the columns it reads; no speculative schema.
  *(Rejected: shipping them in Phase 18 unread — the verifier would correctly flag columns no
  Phase 18 requirement asked for.)*

- **D-13 (user-selected): Phase 18 ships NO way to configure a second guild, and that is the
  intended end state.** With no `/setup` yet, both Phase 18 success criteria are trivially and
  verifiably true: a brand-new guild stays completely silent, and the home guild is unchanged.
  **No stopgap owner-only setter.**
  *(Rejected: a temporary owner-only setter to exercise the seam on a second guild — the live-Discord
  UAT tail is parked behind the residential host anyway, and Phase 19 lands `/setup` immediately
  after: dead code by the next phase.)*

### CI gate (CICD-01)

- **D-14 (user-selected): Ruff — lint + format check — as the single tool.** No lint config
  exists in the repo today (no `pyproject.toml`, `setup.cfg`, `.flake8`, `ruff.toml`, or
  `.pre-commit-config.yaml`), so adoption is greenfield. One tool, one `pyproject.toml` section,
  replacing flake8 + isort + black; fast enough that CI stays in the seconds. **Start near the
  default ruleset and tighten later, not the reverse** — the first run over ~10k LOC will surface
  findings.
  *(Rejected: flake8 + `black --check` — two tools, two configs, and a whole-codebase reformat
  landing in the same phase as a config refactor; pytest-only — descopes half of CICD-01.)*

- **D-15 (user-selected): CI stands up a `pgvector/pgvector:pg16` service container** and sets
  `TEST_DATABASE_URL`, unskipping the ~108 live-DB tests **with zero secrets and zero Neon
  traffic**. `tests/conftest.py:39-45` already reads `TEST_DATABASE_URL` and `pytest.skip`s on
  connection error, so this is a service-container + env addition, not a test rewrite. This
  directly serves the roadmap's stated reason for the gate: **Phase 21's surgery on the scarred
  memory subsystem** (MEM-05 / the Phase 13 CR-01 `expires_at` scar) is exactly the code those
  tests cover.
  > **Researcher must confirm** none of the currently-skipped live-DB tests also require a real
  > `GEMINI_API_KEY` (i.e. that embeddings are faked/stubbed in the live-DB paths). If any do,
  > either stub them or split that subset out — **do not add an API key secret to CI.**

  *(Rejected: pure-suite-only — the memory tests Phase 21 leans on stay unexercised, and "green"
  means less than it looks; a non-blocking second DB job — a job that can never fail is a job
  people learn to ignore.)*

- **D-16 (user-selected): both pytest and Ruff are BLOCKING, and Phase 18 includes the work to
  make the existing ~10k LOC clean under the chosen ruleset.** A gate that can be red on `main`
  is not a gate. **Keep the lint/format cleanup as its own atomic commit**, separate from the
  config-seam refactor, so the refactor stays reviewable.
  *(Rejected: advisory lint — reliably decays into ignored lint; changed-files-only scoping — the
  diff-scoping logic becomes its own maintenance burden.)*

- **D-17 (user-selected): the README build badge lands in Phase 23**, alongside the PORT-03
  README-as-case-study rewrite. The ROADMAP explicitly permits either; adding a badge to a README
  about to be replaced wholesale is churn. Phase 18 ships the workflow; Phase 23 ships the badge
  pointing at it.

### Claude's / Planner's Discretion (do NOT re-ask the user)

- **Exact schema types and defaults** for `guild_config` — column types, `NOT NULL`s, index (if
  any), and whether `updated_at` uses a trigger or an explicit `now()` in each UPDATE. Follow the
  `guild_jams` / `resolution_cache` idiom.
- **Cache data structure** — `dict[int, GuildConfig]` vs a small dataclass in `models/`; whether
  a `models/guild_config.py` dataclass is warranted or an asyncpg `Record` suffices.
- **Exact pure-function signatures** in `logic/guild_config.py` and how many there are (one
  resolver decision + one predicate, or a single function) — so long as they are keyword-only,
  `discord`-free, and mock-free tested.
- **Where the boot seed runs** — inside `setup_hook`, `on_ready` (guarded by `_ready_done`), or a
  dedicated service method called from `bot.py`. Note `bot.get_channel` needs the cache populated,
  which argues for `on_ready`.
- **Ruff ruleset contents**, target-version, per-file ignores, and whether `ruff format` runs as
  `--check` or `--diff`.
- **Workflow YAML structure** — job/matrix layout, Python version(s), pip caching, whether lint
  and test are one job or two.
- **Which ambient surfaces need touching** to route through the new resolver — the grep in
  `<code_context>` is a starting point, not an exhaustive list; verify by call-site.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements (this phase)
- `.planning/ROADMAP.md` §"Phase 18: Per-Guild Config Foundation & CI Gate" — goal, dependencies,
  and the 5 success criteria (note SC-3 names the exact three code sites that must disappear).
- `.planning/REQUIREMENTS.md` §"Per-Guild Configuration (CONFIG)" — CONFIG-01…05, including the
  blockquote that `OWNER_ID` + `ERROR_LOG_CHANNEL_ID` stay **global**.
- `.planning/REQUIREMENTS.md` §"CI/CD (CICD)" — CICD-01 (and CICD-02/03, which Phase 23 extends
  this workflow with).
- `.planning/REQUIREMENTS.md` §"Key Decisions (this milestone)" — the locked
  **"Ambient default-OFF until `/setup`"** decision that D-01 makes structural.
- `.planning/REQUIREMENTS.md` §"Descope Rule" — standing, user-directed. Applies to every phase.

### The code being consolidated (CONFIG-02 — SC-3 names all three)
- `bot.py:103-145` — `_resolve_dexter_channel`: the 4-step fallback chain, with a docstring that
  explicitly admits "Mirrors EventsCog._get_ambient_channel exactly; kept local to bot.py to
  preserve file-ownership boundaries (duplication is acceptable per plan)." This phase revokes
  that allowance.
- `bot.py:515` and `bot.py:739` — the two `_resolve_dexter_channel` call sites (startup message,
  idle-loneliness).
- `cogs/events.py:98-137` — `_get_ambient_channel`: the duplicate.
- `cogs/events.py:266`, `310`, `356` — its three call sites (voice-join roast, and two others).
- `cogs/events.py:443-448` — bare-equality gate #1: the proactive-callback dispatch
  (`message.channel.id == config.DEXTER_CHANNEL_ID`).
- `cogs/events.py:454-460` — bare-equality gate #2: the vision-roast dispatch (same equality,
  plus `message.attachments`).
- `config.py:57` — `DEXTER_CHANNEL_ID = int(os.getenv("DEXTER_CHANNEL_ID") or "0") or None` — the
  value D-08 seeds from and D-09 demotes to a bootstrap-only input.

### Schema + DB idiom (CONFIG-01)
- `database.py` `SCHEMA_SQL` — the idempotent `CREATE TABLE IF NOT EXISTS` block. `guild_jams`
  (Phase 12) and `resolution_cache` (Phase 6) are the closest structural analogs for a new
  guild-keyed table.
- `database.py` — the `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` idiom (`bot_daily_stats.total_errors`,
  Phase 8; `user_profiles.proactive_opt_out`, Phase 16) that D-12 hands to Phase 19.
- `database.py::get_proactive_opt_out` / `set_proactive_opt_out` — the get/set upsert-helper pair
  the `guild_config` helpers should mirror.
- `CLAUDE.md` §"Database Schema (PostgreSQL)" — the authoritative running schema narrative; must be
  updated when `guild_config` lands.

### Service + pure-logic seam conventions (CONFIG-03 / D-04 / D-05)
- `services/memory.py` + its wiring in `bot.py` — the canonical "service constructed in `bot.py`,
  attached as a bot attribute, reached via `self.bot.<name>` from cogs" pattern.
- `services/metrics.py` — `PerfMetrics`, the in-memory-state-owning service analog.
- `logic/proactive.py::should_fire_proactive_callback` — the keyword-only, `discord`-free,
  `random`/`datetime`-free pure gate `logic/guild_config.py` mirrors.
- `logic/vision.py::should_fire_vision_roast` — the most recent instance of the same seam.
- `tests/test_roast_logic.py` — the mock-free test convention to mirror.

### Testing + CI (CICD-01 / D-15)
- `tests/conftest.py:34-46` — reads `TEST_DATABASE_URL` (default documented in the module
  docstring) and `pytest.skip`s on connection error. **This is why a service container unskips the
  live-DB suite with no test changes.**
- `tests/test_database_phase11.py`, `test_database_phase15.py`, `test_database_phase16.py`,
  `tests/test_memory.py` — the `@pytest.mark.skipif(_SKIP_LIVE, ...)` bodies. Verify none need a
  real `GEMINI_API_KEY` before enabling them in CI (D-15 caveat).
- `.planning/codebase/TESTING.md` — the "pure logic gets TDD; Discord/process code is
  untested-by-design, verified by structural review + clean local boot" convention.
- There is **no `.github/` directory and no lint config of any kind** in the repo today — CICD-01
  is greenfield.

### Prior-phase context (conventions this phase inherits)
- `.planning/phases/17-vision-multimodal-roasting/17-CONTEXT.md` — the `logic/` pure-seam +
  silent-skip discipline; the vision-roast dispatch gate this phase re-routes.
- `.planning/phases/16-proactive-memory-callbacks/16-CONTEXT.md` — the proactive-callback dispatch
  gate this phase re-routes; the `proactive_opt_out` column/ALTER precedent D-12 points Phase 19 at.
- `.planning/PROJECT.md` §"Key Decisions" — the full decision ledger; §"Context" for the
  cog → service → model layering and the testing convention.
- `CLAUDE.md` §"Critical Rules" + §"Implementation Gotchas" — notably the Neon pool rules
  (`statement_cache_size=0`, `ssl='require'`) that any CI Postgres container does **not** need but
  the production DSN does; and the `asyncpg` multi-statement DDL rule (Pitfall 1: `SCHEMA_SQL` is
  plain DDL with no `$N` params, applied in one `conn.execute()`).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `bot.py::_resolve_dexter_channel` / `cogs/events.py::_get_ambient_channel` — the two verbatim
  copies. Their 4-step chain body becomes `resolve_announce_channel` (D-02); their ambient callers
  switch to the strict `resolve_ambient_channel` (D-01).
- `database.py::get_proactive_opt_out` / `set_proactive_opt_out` — the get/set upsert-helper shape
  for `guild_config` reads/writes.
- `services/memory.py` wiring in `bot.py` — the exact service-construction + bot-attribute pattern
  `GuildConfigService` copies.
- `logic/proactive.py` / `logic/vision.py` + `tests/test_roast_logic.py` — the pure-gate and
  mock-free-test templates for `logic/guild_config.py`.
- `tests/conftest.py` `TEST_DATABASE_URL` + skip-on-connection-error harness — already CI-ready;
  needs only a service container and one env var (D-15).

### Established Patterns
- **cog → service → model layering**, services constructed in `bot.py` and attached as bot
  attributes; cogs never construct services.
- **`logic/` is the pure seam** (Phase 10 D-02): nondeterminism and I/O computed in glue and passed
  as primitives; the glue dispatches on the returned value and does **not** mirror the branch logic.
- **Idempotent DDL**: `CREATE TABLE IF NOT EXISTS` in `SCHEMA_SQL` for new tables;
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for later additions. `SCHEMA_SQL` is plain, param-free
  DDL applied in a single `conn.execute()` (asyncpg multi-statement rule).
- **"No output beats a wrong output"** — the Phase 17 silent-skip instinct, which D-01/D-03/D-07 all
  extend to the config seam.
- **Testing convention** — pure logic gets mock-free TDD; Discord/process glue is untested-by-design,
  verified by structural review + clean local boot.

### Integration Points
- New `guild_config` table in `database.py::SCHEMA_SQL` + get/set/load-all helpers.
- New `services/guild_config.py::GuildConfigService`, constructed and attached in `bot.py`; cache
  loaded + home-guild seeded at boot (D-06/D-08 — likely `on_ready`, since `bot.get_channel` needs
  a populated cache).
- New `logic/guild_config.py` pure seam + a `tests/test_guild_config_logic.py` mock-free lock.
- Rewrites at `bot.py:103-145`, `bot.py:515`, `bot.py:739`, `cogs/events.py:98-137`,
  `cogs/events.py:266/310/356`, `cogs/events.py:443-448`, `cogs/events.py:454-460`.
- New `.github/workflows/*.yml` (pytest + Ruff, pgvector service container) and a new
  `pyproject.toml` `[tool.ruff]` section.
- **Regression surface:** `tests/test_proactive_events.py:183` and `:202` currently
  `patch("cogs.events.config.DEXTER_CHANNEL_ID", 500)` — they will need to patch the new resolver
  seam instead. Treat any test that patches `DEXTER_CHANNEL_ID` as a call-site inventory.

</code_context>

<specifics>
## Specific Ideas

- **The seam's safety property should be structural, not remembered.** The whole point of D-01 is
  that a future contributor adding a fifth ambient surface *cannot* accidentally make it fire in an
  unconfigured guild, because the resolver simply hands them `None`. If a reviewer ever has to check
  "did you remember to guard this?", the design failed.
- **The two-resolver split (D-02) is the load-bearing idea.** "Where does Dexter *talk*" and "where
  does Dexter *announce itself*" are genuinely different questions with different consent semantics.
  Collapsing them into one function with a boolean is how the fallback chain sneaks back into the
  ambient path six months from now.
- **The env var is being demoted, not deleted.** After D-08/D-09, `DEXTER_CHANNEL_ID` is a one-time
  bootstrap input with no ongoing authority. It should not appear in any resolver, any ambient gate,
  or any hot path — only in the boot seed. A grep for `DEXTER_CHANNEL_ID` in `cogs/` after this phase
  should return **nothing**.
- **"Boring Dexter" is the correct failure mode.** D-07's fail-closed choice means every uncertainty
  in this subsystem resolves toward silence. A Dexter that says nothing is a bug report; a Dexter
  that roasts a stranger's server is an incident.
- **CI's real customer is Phase 21.** D-15's service container is not general hygiene — it is
  specifically so that the memory subsystem's regression tests (the Phase 13 CR-01 `expires_at` scar,
  MEM-05) are actually running when Phase 21 rewrites `search_memories` scoping.

</specifics>

<deferred>
## Deferred Ideas

- **`/setup` + channel dropdown picker** → Phase 19 (ONBOARD-02/03). Explicitly not stubbed here
  (D-13).
- **Per-guild `ambient_roasts_enabled` / `vision_roasts_enabled` toggles** → Phase 19 (ONBOARD-04),
  added by `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (D-12).
- **Readers/setters for `silenced` + `is_blocked`**, `CommandTree.interaction_check` block
  enforcement, and the owner control plane → Phase 20 (OWNER-02/04/05/06). Columns ship now,
  unread (D-11).
- **`on_guild_join` / `on_guild_remove` lifecycle handlers** → Phase 19 (join welcome + owner
  notify) and Phase 21 (MEM-04 purge hangs off removal).
- **README build badge** → Phase 23, with the PORT-03 case-study rewrite (D-17).
- **GitHub Pages CD + GHCR image publish** → Phase 23 (CICD-02/03) — they extend the workflow this
  phase creates.
- **Tightening the Ruff ruleset** beyond the near-default starting set (D-14) — a later cleanup, not
  a Phase 18 blocker.

None of the above are lost — each has a named home in a later v1.4 phase.

</deferred>

---

*Phase: 18-per-guild-config-foundation-ci-gate*
*Context gathered: 2026-07-10*
