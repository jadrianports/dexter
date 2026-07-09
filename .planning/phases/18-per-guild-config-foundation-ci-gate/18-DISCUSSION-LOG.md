# Phase 18: Per-Guild Config Foundation & CI Gate - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-10
**Phase:** 18-per-guild-config-foundation-ci-gate
**Areas discussed:** Fallback-chain fate, Config seam shape & cache, Home-guild seeding, CI gate scope, Forward-column semantics (user-requested 5th area)

Gray areas were presented after loading PROJECT.md / REQUIREMENTS.md / ROADMAP.md / STATE.md and the Phase 15–17 CONTEXT.md files, and after scouting `bot.py`, `cogs/events.py`, `config.py`, `tests/conftest.py`, and the (absent) `.github/` + lint config. The user selected **all four** offered areas, then opened a fifth.

---

## Fallback-chain fate (CONFIG-02 / CONFIG-04)

### Q1: For a guild that HAS configured an ambient channel, how should ambient resolution work?

| Option | Description | Selected |
|--------|-------------|----------|
| Strict: row or silence | Ambient resolves ONLY `guild_config.ambient_channel_id`; no row → None → silent. Kills all 4 fallback steps from the ambient path. Makes CONFIG-04 structural. | ✓ |
| Keep the music-channel step | Config first, then last active music channel. Reintroduces a path where an unconfigured guild gets ambient output the moment someone runs `/play`. | |
| Keep the full chain as a fallback | Config → music → system → first writable. Closest to today, but contradicts the locked "ambient default-OFF until `/setup`" decision. | |

**User's choice:** Strict: row or silence → **D-01**

### Q2: Phase 19's ONBOARD-01 welcome-nudge needs to post in a guild with NO config row. What happens to the fallback chain code?

| Option | Description | Selected |
|--------|-------------|----------|
| Two named functions | Keep the chain, isolated as `resolve_announce_channel`, used only by join-welcome + owner notices. `resolve_ambient_channel` never touches it. CONFIG-02's "one code path" holds per-intent. | ✓ |
| Delete it now, Phase 19 rebuilds | Cleanest Phase 18 diff, but the chain gets re-derived and re-reviewed a phase later. | |
| One resolver with a mode flag | `resolve_channel(guild, allow_fallback=...)`. A boolean that flips a safety property is the kind of arg a future caller passes wrong. | |

**User's choice:** Two named functions → **D-02**

### Q3: A configured guild's `ambient_channel_id` points to a deleted channel, or one where Dexter lost send permission.

| Option | Description | Selected |
|--------|-------------|----------|
| Silent skip, log it | Return None, stay quiet, WARNING to `dexter.log`, row left intact so re-granting permission just works. Matches the Phase 17 silent-skip instinct. | ✓ |
| Silent skip + auto-clear `configured` | More self-healing, but a transient permission blip permanently un-configures a guild. | |
| Fall back to the chain just this once | Rejected: an admin who picked `#bot-spam` did not consent to `#general`. | |

**User's choice:** Silent skip, log it → **D-03**

**Notes:** This area was presented first because the existing 4-step chain is precisely the mechanism that would make Dexter roast strangers minutes after an invite — the abuse surface the Phase 20 kill-switch only mitigates reactively.

---

## Config seam shape & cache (CONFIG-03)

### Q1: Where does the consolidated per-guild config seam live?

| Option | Description | Selected |
|--------|-------------|----------|
| `services/guild_config.py` | `GuildConfigService` wired in `bot.py`, bot attribute, like `memory_service`/`metrics`. Owns cache + both resolvers. One extension point for Phase 19/20's push-invalidate. | ✓ |
| `utils/channels.py` + inline cache | Lighter, but a module-global cache has no obvious owner for invalidation and is harder to test. | |
| Methods on the Bot subclass | Grows `bot.py`; `events.py` would reach through `self.bot` into playback-adjacent code — the duplication CONFIG-02 exists to kill. | |

**User's choice:** `services/guild_config.py` → **D-04**

### Q2: Does the Phase 10 pure-`logic/` convention apply here?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — pure resolve decision | `logic/guild_config.py`, keyword-only, discord-free. Service does I/O, pure fn decides. Locks silent-until-configured under mock-free tests, like `logic/vision.py` and `logic/proactive.py`. | ✓ |
| No — service methods with a fake row | Fewer files, but breaks a convention that caught real scars (Phase 13 CR-01, Phase 16 WR-03). | |

**User's choice:** Yes — pure resolve decision → **D-05**

### Q3: How is the cache populated, and what does a MISS mean?

| Option | Description | Selected |
|--------|-------------|----------|
| Load-all at boot; miss = unconfigured | One `SELECT *` at boot. Miss is authoritative → silent, no DB read. Satisfies CONFIG-03 literally. Phase 19 `on_guild_join` inserts + populates; `/setup` and Phase 20 push-invalidate. | ✓ |
| Lazy read-through on miss | The first ambient event per guild per boot IS a Neon round-trip — the thing CONFIG-03 forbids. | |
| Load-all + lazy fill | Belt-and-suspenders, at the cost of a live-DB path in the hot handler that never gets exercised. | |

**User's choice:** Load-all at boot; miss = unconfigured → **D-06**

### Q4: The boot load fails, or a config write throws (Neon scale-to-zero, timeout).

| Option | Description | Selected |
|--------|-------------|----------|
| Fail closed — silence everywhere | Errored cache → every guild reads unconfigured. Ambient quiet; core commands keep working. Worst case is a boring Dexter, never a Dexter roasting a server that never opted in. | ✓ |
| Fail closed + bounded retry | Same silence plus self-heal, at the cost of another `make_task` loop for a failure a restart already fixes. | |
| Fail open — fall back to env channel | A bug in the load path would silently restore the pre-refactor single-channel world and hide the failure. | |

**User's choice:** Fail closed — silence everywhere → **D-07**

---

## Home-guild seeding (CONFIG-05)

### Q1: `DEXTER_CHANNEL_ID` is a channel id; `guild_config` is keyed by guild id. How does the home guild get its row?

| Option | Description | Selected |
|--------|-------------|----------|
| One-time boot seed, idempotent | Resolve channel → `ch.guild.id`, `INSERT ... ON CONFLICT DO NOTHING` with `configured=true`, refresh cache. Home guild becomes an ordinary tenant; `/setup`, silence, purge all treat it identically. | ✓ |
| Resolver-level env fallback, no row | Zero migration, but the home guild becomes a permanent special case inside the one function every ambient surface calls. | |
| Manual `/setup` after deploy | Breaks CONFIG-05's explicit "current behavior is unchanged after the refactor" promise for one restart window. | |

**User's choice:** One-time boot seed, idempotent → **D-08**

### Q2: The seed runs every boot. What if the owner later moves the channel via `/setup`, or clears the env var?

| Option | Description | Selected |
|--------|-------------|----------|
| `ON CONFLICT DO NOTHING` — env is bootstrap only | The row wins forever. A later `/setup` survives restart; deleting the env var changes nothing. Stops a stale `.env` from silently overriding a deliberate `/setup`. | ✓ |
| `ON CONFLICT DO UPDATE` — env stays authoritative | Makes `/setup` a silently self-reverting no-op in the home guild after any restart. | |

**User's choice:** `ON CONFLICT DO NOTHING` → **D-09**

### Q3: `DEXTER_CHANNEL_ID` unset, or resolves to nothing.

| Option | Description | Selected |
|--------|-------------|----------|
| Skip silently, log at INFO | No row → ambient-silent everywhere until `/setup`. The correct, desirable state for a fresh clone (a recruiter running it) and for CI, where the env var is absent. Not an error. | ✓ |
| Skip, but warn to the error channel | Cries wolf on every fresh deploy where an unset value is intentional. | |
| Refuse to boot | Hostile to the milestone goal — an invitable bot must run fine with no home guild at all. | |

**User's choice:** Skip silently, log at INFO → **D-10**

---

## CI gate scope (CICD-01)

**Scout finding presented to the user:** the live-DB tests key off `TEST_DATABASE_URL` and self-skip on connection error (`tests/conftest.py:45`), so a service container could unskip all ~108 with no secrets. There is no `.github/` directory and no lint config of any kind in the repo.

### Q1: What does CI's lint step run?

| Option | Description | Selected |
|--------|-------------|----------|
| Ruff, lint + format check | One tool, one `pyproject.toml` section, replaces flake8+isort+black. Greenfield adoption; start near-default and tighten later. | ✓ |
| flake8 + `black --check` | Two tools, two configs, and a whole-codebase reformat landing in the same phase as a config refactor. | |
| No lint — pytest only | Descopes half of CICD-01. | |

**User's choice:** Ruff → **D-14**

### Q2: Should CI stand up a Postgres+pgvector service container?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — pgvector service container | `pgvector/pgvector:pg16` + `TEST_DATABASE_URL` unskips the live-DB suite, zero secrets, zero Neon traffic. Serves the roadmap's stated reason for the gate: Phase 21's memory-subsystem surgery (MEM-05 / CR-01 scar). | ✓ |
| No — pure suite only | Fastest, but the memory tests Phase 21 leans on stay unexercised; "green" means less than it looks. | |
| Both jobs, DB job non-blocking | A job that can never fail is a job people learn to ignore. | |

**User's choice:** Yes — pgvector service container → **D-15**
**Notes:** Flagged as a research task for `/gsd:plan-phase` — the researcher must confirm none of the currently-skipped live-DB tests also require a real `GEMINI_API_KEY`. If any do, stub or split them; **do not add an API key secret to CI.**

### Q3: How strict is the gate on a first run over ~10k LOC?

| Option | Description | Selected |
|--------|-------------|----------|
| Both blocking; fix findings in this phase | A gate that can be red on `main` is not a gate. Cleanup lands as its own atomic commit so the refactor stays reviewable. | ✓ |
| Tests blocking, lint advisory | Advisory lint reliably decays into ignored lint. | |
| Both blocking, lint scoped to changed files | Diff-scoping logic becomes its own maintenance burden. | |

**User's choice:** Both blocking → **D-16**

### Q4: README build badge — now or Phase 23?

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 23, with the README rewrite | ROADMAP permits either. PORT-03 replaces the README wholesale; badging a doomed README is churn. | ✓ |
| Now, in Phase 18 | Immediate visible signal, cannot be forgotten later. | |

**User's choice:** Phase 23 → **D-17**

---

## Forward-column semantics (user-requested 5th area)

Offered at the wrap-up checkpoint as a gray area I had not raised; the user chose to discuss it rather than proceed straight to CONTEXT.md.

### Q1: CONFIG-01 lists `silenced` + `is_blocked`, which only Phase 20 reads. Does Phase 18 create them?

| Option | Description | Selected |
|--------|-------------|----------|
| Create them, don't read them | CONFIG-01 names them explicitly. Ship with `false` defaults; Phase 20 adds readers, setters, and tests together. | ✓ |
| Create them AND wire `is_blocked` into the resolver now | Ships a kill-switch enforcement path with no way to set the flag and no test of the owner flow — dead code that looks live. | |
| Only ship what Phase 18 reads | Smallest honest diff, but contradicts CONFIG-01's literal column list. | |

**User's choice:** Create them, don't read them → **D-11**

### Q2: ONBOARD-04's per-guild roast/vision toggles have no column in CONFIG-01. Where do they land?

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 19 ALTERs them in | Same idiom as `bot_daily_stats.total_errors` (P8) and `user_profiles.proactive_opt_out` (P16). Each phase owns the columns it reads; no speculative schema. | ✓ |
| Phase 18 ships them too | Saves an ALTER, but Phase 18's schema would contain columns no Phase 18 requirement asked for — the verifier would flag them. | |

**User's choice:** Phase 19 ALTERs them in → **D-12**

### Q3: With no `/setup`, no guild but the seeded home guild can become configured. Intended?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — that IS success criterion 1 | Phase 18 is a seam, not a feature. Both success criteria are trivially and verifiably true. No stopgap setter. | ✓ |
| Add a minimal owner-only setter | Useful for live UAT, but that tail is parked behind the residential host anyway, and Phase 19 lands `/setup` immediately after. Dead code by the next phase. | |

**User's choice:** Yes — that IS success criterion 1 → **D-13**

---

## Claude's Discretion

Captured in CONTEXT.md `<decisions>` § "Claude's / Planner's Discretion" — do not re-ask the user:

- Exact `guild_config` schema types, defaults, `NOT NULL`s, indexes, and `updated_at` mechanism.
- Cache data structure (plain dict of asyncpg `Record` vs a `models/guild_config.py` dataclass).
- Exact pure-function signatures and count in `logic/guild_config.py`.
- Where the boot seed runs (`setup_hook` vs `on_ready` — `bot.get_channel` argues for `on_ready`).
- Ruff ruleset contents, target-version, per-file ignores, `--check` vs `--diff`.
- Workflow YAML structure: job/matrix layout, Python versions, pip caching, one job or two.
- The exhaustive inventory of ambient surfaces needing re-routing (verify by call-site; the grep in `<code_context>` is a starting point).

## Deferred Ideas

- `/setup` + channel dropdown picker → Phase 19 (ONBOARD-02/03).
- Per-guild `ambient_roasts_enabled` / `vision_roasts_enabled` toggles → Phase 19 (ONBOARD-04).
- Readers/setters for `silenced` + `is_blocked`, `CommandTree.interaction_check` enforcement, owner control plane → Phase 20.
- `on_guild_join` / `on_guild_remove` lifecycle handlers → Phase 19 (welcome + owner notify) and Phase 21 (MEM-04 purge).
- README build badge → Phase 23 (D-17).
- GitHub Pages CD + GHCR image publish → Phase 23 (CICD-02/03), extending this phase's workflow.
- Tightening the Ruff ruleset beyond the near-default starting set → later cleanup, not a Phase 18 blocker.

No scope creep occurred — every idea raised mapped to an already-roadmapped later phase.
