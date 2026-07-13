# Phase 21: Memory Scoping & Guild Data Lifecycle - Context

**Gathered:** 2026-07-14
**Status:** Ready for planning

> **Session note:** All four gray areas below were **explicitly selected by the user** for
> discussion, and each decision (D-01…D-04) is the **user's affirmative choice of the recommended
> option** — not an AFK adoption. Numeric/structural minutiae and the exact recall-seam signature
> remain planner discretion per the Phase 11/13/14/15/16/17/18/19/20 precedent.
>
> This phase does the memory surgery Phases 18–20 deliberately deferred to it. It is the phase the
> standing **Descope Rule** names with particular force, because it touches
> `services/memory.py::search_memories`/`recall()` — the `user_id`-only-scoped code that produced
> the **Phase 13 CR-01 blocker**. The decisions below are chosen specifically to keep that scarred
> path untouched.

<domain>
## Phase Boundary

Phase 21 delivers **hybrid memory scoping + a guild-data purge**: a third party's recalled memory
stops leaking across servers, and a departed guild's data can't resurface on re-invite — **without
assuming the ideal scoping ships** (MEM-01/03/05 are a hypothesis, not a contract).

**In scope:**
- **MEM-01** — `/roast @user`, ambient roasts, and proactive callbacks recall only memories scoped
  to the current guild (a third party's memories never travel between servers). Implemented on the
  **read path only** (D-02).
- **MEM-02** — `/ask` continues to recall the **invoker's own** memory **globally**, completely
  unaffected by the scoping change (self-scoped — no cross-user exposure is possible).
  **Unconditionally shippable regardless of how the rest of the phase resolves.**
- **MEM-03** — legacy `guild_id = NULL` memories (the `daily_batch` corpus) are handled by an
  explicit, tested backward-compat rule — **grandfathered as globally-recallable** (D-01), never
  silently blinded.
- **MEM-04** — when Dexter leaves or is force-left from a guild, that guild's `guild_config`,
  `guild_queues`, `guild_jams`, and guild-scoped (`guild_id = $1`) `user_memories` rows are purged.
  **Unconditionally shippable.**
- **MEM-05** — guild-scoped search does not corrupt cross-kind dedup or `expires_at` semantics; the
  Phase 13 CR-01 scar is locked by regression test.
- **PROJECT.md Key Decisions** records whichever path actually shipped, so **PORT-04** (Phase 23)
  can disclose it honestly.

**Out of scope (belongs to later phases / future milestone):**
- `/ask` guild-scoping, or per-user opt-in cross-guild sharing → **MEM-F3** (Future Requirements,
  revisit if Dexter outgrows modest scale). `/ask` stays global this phase (MEM-02).
- Vision → RAG memory persistence → **MEM-F2** (deferred out of v1.3).
- Salience reinforcement → **MEM-F1**.
- Touching `guild_blocklist` in the purge — **explicitly forbidden** (Phase 20 D-01): the purge
  deletes guild data freely while a kicked abuser's block **survives** (OWNER-04).
- `/invite` + OAuth2 URL → Phase 22. Landing page / README / PORT-04 disclosure copy → Phase 23
  (this phase only records the decision PORT-04 will disclose).

</domain>

<decisions>
## Implementation Decisions

### Legacy NULL corpus — the MEM-03 backward-compat rule

- **D-01 (user-selected): grandfather `guild_id = NULL` rows as globally-recallable.** The
  guild-scoped recall filter becomes `WHERE user_id = $1 AND (guild_id = $2 OR guild_id IS NULL)`.
  New guild-stamped memories are guild-scoped; the pre-existing `NULL` corpus (essentially
  `daily_batch`, which writes `guild_id=None`) stays recallable everywhere. This satisfies MEM-03's
  "the existing memory corpus is not silently made unrecallable" and is the **tested backward-compat
  rule** MEM-03 demands.
  *(Rejected: **strict `guild_id = $1` only** — cleanest scoping but silently blinds the entire
  pre-existing NULL corpus to ambient/roast recall, in direct tension with MEM-03. Rejected:
  **one-time backfill migration** stamping NULL rows with a guild_id — `daily_batch` memories have
  no attributable single guild, so it cannot be done correctly; this is a descope tripwire, not a
  path.)*
  **Scouting finding that makes D-01 low-risk:** every *unprompted write surface* already stamps a
  real `guild_id` at write time (`repeat_song`/`milestone` in `cogs/music.py`, `auto_queue_ignored`
  in `cogs/ai.py`, the ambient roast kinds in `cogs/events.py`). Only `services/memory.py`'s
  `daily_batch` distill passes `None`. So the NULL corpus that D-01 grandfathers is narrow and known.

### Scoping blast radius — staying clear of the CR-01 scar (MEM-05)

- **D-02 (user-selected): add the guild filter to the READ path ONLY.** Only
  `MemoryService.recall()` / `database.search_memories()` (the ANN read) gain the
  `(guild_id = $2 OR guild_id IS NULL)` clause. `remember()` / dedup (`search_memories` k=1) /
  eviction / the D-05 `expires_at` self-refresh stay **fully `user_id`-scoped and byte-identical** —
  the exact CR-13-01-scarred path is **not touched**. MEM-05's regression test locks that adding
  the guild read filter did **not** leak into cross-kind dedup or `expires_at` semantics.
  *(Rejected: **also guild-scope dedup + eviction** — nominally "more correct" per-guild dedup, but
  it reopens the exact `expires_at`/cross-kind corruption scar Phase 13 CR-01 recorded and enlarges
  the regression surface, for negligible gain: dedup/eviction operate over a *single user's own*
  facts, so cross-guild dedup of that user's own memories is harmless, and cap-eviction is a
  per-user budget concept that should stay global.)*
  **Seam consequence (planner discretion, flagged):** because `/roast`+ambient+proactive have a
  `guild_id` AND want scoping, while `/ask` ALSO has a `guild_id` (`interaction.guild_id`) but must
  stay global (MEM-02), **guild_id presence alone cannot distinguish the two.** `recall()` needs an
  **explicit opt-in** to guild-scoping (a keyword flag / dedicated scope param), NOT reuse of the
  existing positional `guild_id` arg (which the docstring calls "reserved for future scoping" — this
  is that future, but it can't be auto-derived). The planner picks the exact signature; see the
  call-site inventory in `<code_context>`.

### Guild-data purge — scope and hook (MEM-04)

- **D-03 (user-selected): purge `guild_id = $1` rows only, via a single `on_guild_remove` hook.**
  The purge deletes `guild_config`, `guild_queues`, `guild_jams`, and `user_memories WHERE
  guild_id = $1` — **`NOT NULL`**, so the grandfathered global corpus (D-01) survives. A **single
  hook in `bot.py::on_guild_remove`** covers every departure path: a natural kick/leave AND the
  Phase 20 `/guilds leave` / `/guilds block` force-leave both call `guild.leave()`, which fires
  `on_guild_remove`. The purge **never touches `guild_blocklist`** (Phase 20 D-01) — a blocked
  abuser's block outlives the purge (OWNER-04). Wrapped so a purge failure is logged/swallowed and
  **cannot crash the removal** (mirrors the WR-04 try/except discipline already in `on_guild_join`).
  *(Rejected: **also purge the guild's share of NULL rows** — NULL rows can't be attributed to a
  guild, so there is no correct "this guild's share." Rejected: **hook each teardown site
  separately** (`on_guild_remove` + `ops.py` leave + block) — redundant, since `guild.leave()`
  already fires `on_guild_remove`, and it risks a double-delete or a missed path.)*
  **Ordering note (verify at plan time):** in the `/guilds block` flow the blocklist insert happens
  after `guild.leave()`; `on_guild_remove` (hence the purge) may run concurrently. Because
  `guild_blocklist` is a **separate table the purge never targets**, the ordering is safe — but the
  planner should confirm the purge helper's table list explicitly excludes `guild_blocklist`.

### Descope framing (standing Descope Rule)

- **D-04 (user-selected): attempt the full hybrid scoping; descope to the global fallback only when
  a named tripwire actually hits.** Ship **MEM-02** (`/ask` global) and **MEM-04** (purge)
  unconditionally. Attempt **MEM-01/03/05** — the scouting findings (writes already carry
  `guild_id`; D-02's read-path-only approach sidesteps the scar; D-01 is a narrow, tested NULL rule)
  make the hybrid look **genuinely tractable**, not heroic. The researcher/planner descope a
  specific requirement to the documented fallback **"keep memory global + disclose"** ONLY if one of
  the REQUIREMENTS.md tripwires genuinely fires at plan time (no clean NULL rule; guild-scoped read
  can't be made safe against the scar; purge can't separate guild- from user-scoped rows). Per the
  standing user-directed Descope Rule, that descope needs **no further user permission** — record it
  in PROJECT.md Key Decisions and continue.
  *(Rejected: **pre-authorize straight-to-fallback** — skip the scoping attempt and ship only
  MEM-02 + MEM-04 with global memory disclosed. Lowest risk, but it leaves the third-party leak
  MEM-01 names unaddressed *precisely when the code path now looks safe to fix* — a premature
  surrender of the milestone's stated hybrid-scoping value.)*

### Claude's / Planner's Discretion (do NOT re-ask the user)

- **Exact `recall()` / `search_memories()` signature for the guild-scoping opt-in** — a keyword flag
  (`guild_scoped: bool`), a dedicated `scope_guild_id: str | None`, or similar. Must stay
  keyword-only where it matters, preserve byte-identical behavior for callers that don't opt in
  (MEM-02 `/ask`, and any global surface), and keep the pure-logic conventions. The existing
  positional `guild_id` arg on `recall()` may be repurposed or supplemented — planner's call.
- **The exact call-site inventory** of which `recall()` sites opt into guild-scoping vs stay global
  (see `<code_context>` — MEM-01 names `/roast @user` + ambient roasts + proactive callbacks; the
  music-command memory callback and the auto-queue taste-blend recall are **research items** —
  decide per MEM-01's letter, don't guess).
- **Whether guild-scoping is a new branch in `database.search_memories` SQL** (conditional clause,
  like the existing `kind` clause) vs a new helper — follow the Phase 14 `kind`-clause precedent
  (omit the clause entirely when not opted in, never emit a degenerate `guild_id IS NULL`-only form
  that would break existing recalls).
- **The purge helper shape** — one `purge_guild_data(pool, guild_id)` that runs the four DELETEs, vs
  per-table helpers; transaction vs sequential; DELETE ordering. Follow the `delete_blocklist` /
  `delete_all_user_memories` idiom. New helpers are needed — no per-guild delete exists yet for
  `guild_queues` / `user_memories` (only `guild_jams` has a name-scoped delete, and
  `delete_blocklist`).
- **Exact regression-test shape for MEM-05** — mock-free where the logic is pure; live-DB (CI's
  pgvector service container runs these) for the search/dedup/expires_at interaction. Lock that a
  guild-scoped read leaves the k=1 dedup search and the D-05 `refresh_memory_expiry` byte-identical.
- **Whether any pure `logic/` seam is warranted** (e.g. a `decide_memory_scope`-style predicate) vs
  keeping the opt-in as a plain kwarg — so long as glue dispatches on the return value and doesn't
  mirror branch logic (Phase 10 D-02). Likely overkill here; planner decides.
- **Copy / disclosure wording** for PORT-04 is Phase 23's — this phase only records the decision.

### Reviewed Todos
None — `todo.match-phase 21` returned zero matches.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements (this phase)
- `.planning/ROADMAP.md` §"Phase 21: Memory Scoping & Guild Data Lifecycle" — goal, dependencies
  (Phase 18 config, Phase 20 `on_guild_remove`/force-leave hook), and the 4 success criteria. Note
  SC explicitly frames **MEM-01/03/05 as "a hypothesis, not a contract; see Descope Rule"**.
- `.planning/REQUIREMENTS.md` §"Memory Scoping & Guild Data Lifecycle (MEM)" — MEM-01…05 verbatim,
  plus the **"Needs research at plan time"** callout naming `services/memory.py::search_memories`/
  `recall()`, the `guild_id = NULL` backward-compat rule, dedup-search scoping, and
  `MEMORY_MAX_PER_USER` eviction semantics as the things to resolve before implementation.
- `.planning/REQUIREMENTS.md` §"Descope Rule" — **standing, user-directed**; applies with particular
  force to MEM-01/03/05. Names the three specific tripwires (D-04) and the documented fallback
  ("keep memory global + disclose"). MEM-04 + MEM-02 are independently shippable regardless.
- `.planning/REQUIREMENTS.md` §"Key Decisions (this milestone)" — **"Hybrid memory scoping"** and
  **"Purge guild data on removal"** rows: the locked intent this phase implements. §"Future
  Requirements → Memory" (MEM-F1/F2/F3) — where the deferred memory work lives.

### The Phase 13 CR-01 scar (READ BEFORE TOUCHING THE MEMORY READ PATH)
- `services/memory.py::recall` (`:60`) — currently takes `guild_id` positionally but **ignores it**
  (docstring: "reserved for future per-guild memory scoping; currently the ANN scopes to user_id
  only"). D-02 makes this the guild-scoping seam — but via an **explicit opt-in**, not by
  auto-using this positional arg (MEM-02 `/ask` passes a real guild_id and must stay global).
- `services/memory.py::remember` (`:188`), esp. the **dedup branch (`:248`–`:286`)** — the k=1
  `search_memories` is `user_id`-scoped, and the **D-05 `expires_at` self-refresh gates on the
  MATCHED ROW's kind, not the incoming write's kind (CR-13-01)**. D-02 keeps this path untouched.
  Read the inline comment block at `:265`–`:274` — it is the scar's own description.
- `database.py::search_memories` (`:1333`) — the ANN SQL. Note the **Phase 14 `kind`-clause
  precedent** (`:1355`–`:1361`, `:1377`–`:1378`): an optional filter that is **omitted ENTIRELY**
  when not requested, never emitted as a degenerate `IS NULL`. D-01/D-02's guild clause follows this
  exact discipline. The `WHERE user_id = $1` cross-user guard (`:1347`) is load-bearing — the guild
  clause narrows *within* it, never widens.
- `database.py::refresh_memory_expiry` (`:1469`) — the D-05 `expires_at`-only UPDATE that MEM-05's
  regression test must prove stays byte-identical.
- `.planning/phases/13-*/` CONTEXT/RESEARCH (CR-01 origin) — the cross-kind `expires_at` corruption
  the guild-scoped search must not reintroduce.

### MEM-04 purge — hook + teardown + blocklist exclusion
- `bot.py::on_guild_remove` (`:762`) — currently evicts the cache entry only, **NO DB write** (Phase
  19 D-12). The purge (D-03) hooks HERE. The existing docstring even names the constraint: "Phase 21
  must also preserve a blocked guild's row (or move the blacklist to its own table)" — **Phase 20
  D-01 already moved it**, so the purge is now unconstrained on the guild-data tables.
- `cogs/ops.py::_force_leave_teardown` (`:520`) — the `/guilds leave` + `/guilds block` teardown
  (bump `_play_generation` → `queue.clear()` → `clear_persisted` → voice stop/disconnect →
  `guild.leave()`). Both call `guild.leave()`, so `on_guild_remove` fires — **do not add a second
  purge here** (D-03).
- `cogs/ops.py` `/guilds block` flow (`:594` region) — teardown → `guild.leave()` → blocklist
  insert. The purge must exclude `guild_blocklist` so the block outlives it (OWNER-04).
- `database.py` — existing delete idiom to mirror: `delete_blocklist` (`:725`),
  `delete_all_user_memories` (`:1624`), the `guild_jams` name-scoped delete (`:1306`). **No per-guild
  delete exists yet** for `guild_queues` or guild-scoped `user_memories` — new helpers needed.
- `database.py::SCHEMA_SQL` — the tables the purge touches: `guild_config`, `guild_queues`,
  `guild_jams`, `user_memories`. And `guild_blocklist` — the table it must NOT touch.

### Memory write surfaces (confirm guild_id at write time — MEM-03 scope)
- `cogs/music.py:~1328/1358/1398` — `repeat_song` + `milestone` distill_and_remember, **pass
  `guild_id=str(interaction.guild.id)`** (guild-stamped).
- `cogs/ai.py:~509` — `auto_queue_ignored` distill, **passes `guild_id=str(guild.id)`**.
- `cogs/events.py:~286` — ambient roast kinds distill, **pass `guild_id=str(guild.id)`**.
- `services/memory.py:~387` — `daily_batch` distill inside `distill()`/`distill_and_remember`,
  **passes `guild_id=None`** → the NULL corpus D-01 grandfathers.

### recall() call-site inventory (which opt into guild-scoping — D-02)
- **Guild-scope (MEM-01):** `cogs/ai.py:~220` (`/roast @user`, target-scoped),
  `cogs/events.py:~163` (ambient roast), `cogs/events.py:~514` (proactive callback).
- **Stay global:** `cogs/ai.py:~134` (`/ask`, MEM-02 — invoker self-recall).
- **Research items (decide per MEM-01's letter, don't guess):** `cogs/music.py:~1232` (the
  `MEMORY_CALLBACK_CHANCE`-gated music-command memory callback — currently passes `""` for guild_id)
  and the auto-queue positive-taste-blend recall over voice members' `taste_episode` (a room-taste
  read of *other* users' guild-stamped taste — is it a third-party leak vector or legitimately
  room-scoped?).

### Prior-phase context (conventions this phase inherits)
- `.planning/phases/20-owner-control-plane-rate-observability/20-CONTEXT.md` — **read D-01 in full**:
  `guild_blocklist` is its own table precisely so this phase's purge stays a clean
  `DELETE ... WHERE guild_id = $1` with no "except if blocked" carve-out. Also the `<deferred>`
  section, which hands MEM-04 to this phase with the blocklist explicitly out of purge scope.
- `.planning/phases/19-onboarding-admin-setup/19-CONTEXT.md` §D-12 — the original landmine (a blocked
  guild's entry must survive `on_guild_remove`) that Phase 20 D-01 resolved; the WR-04 try/except
  discipline on `on_guild_join` the purge wrapping should mirror.
- `.planning/PROJECT.md` §"Key Decisions" — the full ledger; the phase-close step must **add the
  actual shipped memory-scoping decision here** (SC-4 / PORT-04 dependency).
- `CLAUDE.md` §"Critical Rules" 11–16 (memory rules) + §"Implementation Gotchas → Phases 9–12/13–17"
  (the `search_memories`/`recall` `kind`-clause discipline, the accuracy firewall, the CR-01 scar
  description) + §"Database Schema" (the running schema narrative to update when purge helpers land).

### Testing + CI
- `tests/conftest.py:34-46` — `TEST_DATABASE_URL` + skip-on-connection-error; Phase 18's CI supplies
  a `pgvector/pgvector:pg16` service container so the new live-DB purge + guild-scoped-search tests
  **actually run**.
- `.github/workflows/ci.yml` — the blocking Ruff + pytest gate every commit runs behind.
- `.planning/codebase/TESTING.md` — "pure logic gets mock-free TDD; Discord/process glue is
  untested-by-design (structural review + clean boot)."
- **Known regression surface:** any test exercising `recall()` / `search_memories` / `remember()`
  dedup / the D-05 `expires_at` self-refresh, and every test mocking those. The guild read filter is
  a call-site inventory across `tests/test_memory*.py` / `tests/test_database_phase1*.py`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `database.py::search_memories` (`:1333`) — the ANN read the guild clause extends, following the
  existing optional-`kind`-clause pattern (omit entirely when not opted in).
- `database.py::delete_blocklist` / `delete_all_user_memories` / the `guild_jams` name-scoped delete
  — the DELETE-helper idiom the new purge helpers mirror.
- `bot.py::on_guild_remove` (`:762`) — the single purge hook (D-03); already fires on force-leave.
- `cogs/ops.py::_force_leave_teardown` (`:520`) — the force-leave path that funnels through
  `guild.leave()` → `on_guild_remove`; **not** a second purge site.
- `services/memory.py::recall` (`:60`) — the read seam that gains an explicit guild-scoping opt-in.

### Established Patterns
- **`WHERE user_id = $1` is the load-bearing cross-user guard** — the guild clause narrows within it,
  never widens (T-11-03a).
- **Optional SQL clause omitted-entirely-when-unset** (Phase 14 `kind` precedent) — never a
  degenerate `IS NULL`-only filter that silently breaks existing recalls.
- **Read/write asymmetry is acceptable** (D-02): recall guild-scopes; remember/dedup/eviction stay
  user-scoped. Cap-eviction (`MEMORY_MAX_PER_USER`) is a per-user budget, correctly global.
- **Additive idempotent DDL only** — no new tables needed here; the purge is DELETEs. No `DROP`.
- **Best-effort, crash-proof lifecycle hooks** (WR-04) — the purge is wrapped; a failure logs and
  is swallowed, never crashing `on_guild_remove`.
- **Purge never touches `guild_blocklist`** (Phase 20 D-01) — the one hard cross-phase invariant.

### Integration Points
- `database.py::search_memories` — new conditional guild clause `(guild_id = $N OR guild_id IS NULL)`.
- `services/memory.py::recall` — new explicit guild-scoping opt-in kwarg; threaded to search_memories.
- `cogs/ai.py` (`/roast`), `cogs/events.py` (ambient + proactive) — opt into guild-scoping; `/ask`
  in `cogs/ai.py` stays global (MEM-02). Two research-item sites (music callback, auto-queue taste).
- `database.py` — new `purge_guild_data`-style helper(s) for the four tables.
- `bot.py::on_guild_remove` — call the purge (wrapped) after the existing cache-evict + owner notice.
- **Regression surface:** every test over `recall`/`search_memories`/`remember` dedup/`expires_at`.

</code_context>

<specifics>
## Specific Ideas

- **The read/write asymmetry is the load-bearing insight.** Scoping the *read* (recall) contains the
  actual leak MEM-01 names — a third party's memory surfacing in the wrong server — while leaving the
  *write/dedup/eviction* path (the Phase 13 CR-01 scar) byte-identical. Every "more correct" instinct
  to also guild-scope dedup or eviction reopens the exact fragility that produced the last blocker,
  for a gain that doesn't exist: a user's own facts deduping across guilds is harmless.

- **`guild_id` presence can't be the scoping signal.** Both `/roast` (scope) and `/ask` (global) run
  in a guild. The opt-in must be an explicit, per-call-site decision — never inferred from whether a
  guild_id happens to be non-null. This is the single subtlety most likely to cause a silent MEM-02
  regression if the planner takes the lazy path.

- **The NULL corpus is small and known, which is why grandfathering it is honest.** Only
  `daily_batch` writes NULL; every unprompted surface already stamps a guild. So `guild_id IS NULL`
  in the recall filter grandfathers a bounded, understood set — not an open-ended "everything old
  leaks everywhere" hole.

- **One hook, one invariant.** The whole MEM-04 story is "`on_guild_remove` purges `guild_id = $1`
  across four tables and never touches `guild_blocklist`." Phase 20 D-01 already earned the clean
  `DELETE` — this phase just spends it. If a reviewer has to reason about "except if blocked," the
  design regressed.

- **This is the phase the Descope Rule was written for — and it looks winnable.** The rule exists
  because MEM touches the scarred subsystem. But the scouting says the write path already carries
  guild_id, the read-path-only approach dodges the scar, and the NULL rule is narrow. Attempt it
  (D-04); the fallback is there and honest if a tripwire actually fires.

</specifics>

<deferred>
## Deferred Ideas

- **Full guild-scoped `/ask`, or per-user opt-in cross-guild sharing** → **MEM-F3** (Future
  Requirements). `/ask` stays global this phase — self-scoped, no cross-user leak possible.
- **Vision → RAG memory persistence** → **MEM-F2** (deferred out of v1.3).
- **Salience reinforcement (surfaced/hit memories gain durability)** → **MEM-F1**.
- **Guild-scoping dedup / eviction** → deliberately rejected here (D-02); revisit only if a real
  cross-guild dedup problem is ever observed (none expected — dedup is per-user).
- **Ripping out the dead `guild_config.is_blocked` column** → left in place since Phase 20 D-03; a
  later cosmetic cleanup at most, never a Phase 21 concern.
- **PORT-04 disclosure copy** (the honest write-up of whichever scoping shipped) → **Phase 23**.
  This phase records the decision in PROJECT.md Key Decisions; Phase 23 discloses it.

### Reviewed Todos (not folded)
None — `todo.match-phase 21` returned zero matches.

</deferred>

---

*Phase: 21-memory-scoping-guild-data-lifecycle*
*Context gathered: 2026-07-14*
