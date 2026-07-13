# Phase 21: Memory Scoping & Guild Data Lifecycle - Research

**Researched:** 2026-07-14
**Domain:** RAG memory read-path scoping (pgvector ANN over `user_memories`) + best-effort guild-data lifecycle purge (asyncpg DELETEs), Python 3.11 / discord.py 2.7.1 / asyncpg 0.31.0
**Confidence:** HIGH — every claim below is a direct code read (file:line cited) or a direct test read; zero new dependencies; zero unverified library-API claims.

## Summary

This phase is pure surgery on existing, working code — no new libraries, no new tables, no new
Gemini call sites. There are exactly two deliverables: (1) an explicit, keyword-only opt-in on
`MemoryService.recall()` / `database.search_memories()` that narrows the ANN read to
`(guild_id = $N OR guild_id IS NULL)` when a call site asks for it, wired into the three
MEM-01-named surfaces plus two research-item call sites this document resolves; and (2) a new
`purge_guild_data()` helper wired into the existing (already-firing) `bot.py::on_guild_remove`
hook that deletes `guild_id = $1` rows from four tables and explicitly never touches
`guild_blocklist`.

The scarred subsystem (Phase 13 CR-01: `remember()`'s dedup branch gating the D-05
`expires_at` self-refresh on the matched row's `kind`) is provably untouched by this design,
because D-02 confines the new clause to the read path (`recall`/`search_memories`) and
`remember()`'s own `search_memories` call (services/memory.py:249) never passes the new
parameter — it stays a two-argument-plus-`k` call exactly as today. Existing test doubles that
monkeypatch `database.search_memories` with a fixed keyword-only signature (e.g.
`tests/test_memory_taste.py:156` `async def fake_search(pool, *, user_id, query_embedding, k)`)
continue to work unmodified because `remember()` never passes the new keyword at all — this is
the load-bearing implementation detail the whole "byte-identical for non-opting callers" promise
depends on, not just a doc comment.

Both CONTEXT-flagged "research items" resolve the same way once the actual discriminating
signal is identified: it is **not** "self vs. third-party by user id" (all three MEM-01-named
surfaces except `/roast @user` actually recall the *same* user who triggered the event — see
Architecture Patterns below) — it is **"explicit synchronous self-pull" (stays global) vs.
"unprompted/ambient broadcast to a channel" (scopes)**. Under that test, both the
`cogs/music.py:1232` earned-roast callback and the auto-queue positive-taste blend
(`cogs/ai.py:332-350`) are ambient broadcasts and should opt in.

**Primary recommendation:** Add a keyword-only `guild_scoped: bool = False` parameter to
`MemoryService.recall()`; thread it into `database.search_memories()` as an optional `guild_id`
keyword that is appended to `params`/the SQL clause **only when truthy** (never as a bare
`None`-defaulted kwarg unconditionally forwarded) — mirroring the Phase 14 `kind`-clause
discipline exactly. Attempt the full hybrid scoping (D-04); none of the three named descope
tripwires fire against the actual code (see Descope Tripwires below).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| ANN read scoping (guild filter) | API / Backend (`services/memory.py`, `database.py`) | — | Pure data-access-layer change; no Discord-object dependency |
| Call-site opt-in decision (which surfaces scope) | API / Backend (cogs, thin glue) | — | A per-call-site boolean literal, not business logic — no new `logic/` seam needed (see Validation Architecture) |
| Guild-data purge | API / Backend (`database.py` helper) | Discord event glue (`bot.py::on_guild_remove`) | The DELETE logic is pure SQL/asyncpg; the *trigger* is a Discord gateway event, already wired |
| Blocklist exclusion invariant | Database / Storage (schema: separate `guild_blocklist` table, Phase 20 D-01) | — | Structural — the purge's table list simply omits this table; no runtime check needed |

## Standard Stack

No new dependencies. Confirmed versions already pinned in `requirements.txt`:

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|---------------|
| discord.py | >=2.3.0 (installed 2.7.1, per Phase 20 research) | `on_guild_remove` event, gateway | Already the project's only Discord binding [VERIFIED: requirements.txt:1] |
| asyncpg | ==0.31.0 | DELETE/SELECT execution, transactions | Already the project's only Postgres driver [VERIFIED: requirements.txt:3] |
| pgvector | >=0.3.6,<0.5 | cosine ANN operator (`<=>`) on `user_memories.embedding` | Already registered via `register_vector` at pool creation [VERIFIED: requirements.txt:14] |

**Installation:** None — zero new packages this phase.

## Package Legitimacy Audit

**N/A this phase.** No external packages are installed. The Package Legitimacy Gate protocol is
skipped per its own trigger condition ("whenever this phase installs external packages").

## Architecture Patterns

### System Architecture Diagram

```
                    ┌─────────────────────────────────────────────────────┐
                    │             MemoryService.recall()                  │
                    │        services/memory.py:60-182                    │
                    │                                                     │
  caller ─────────▶ │  guild_scoped: bool = False  (NEW, keyword-only)    │
  (5 sites below)    │                                                     │
                    │  1. embed(query_text)  [unchanged]                  │
                    │  2. database.search_memories(                      │
                    │       user_id=..., query_embedding=..., k=...,      │
                    │       kind=kind,                                    │
                    │       guild_id=guild_id if guild_scoped else None)  │◀── opt-in signal
                    │     [NEW: guild_id kwarg only appended when         │      lives HERE
                    │      guild_scoped=True — never passed bare]         │
                    │  3-7. floor/rerank/cap/bump  [unchanged]            │
                    └─────────────────────────────────────────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────────────────────┐
                    │       database.search_memories()                   │
                    │       database.py:1333-1390                        │
                    │                                                     │
                    │  WHERE user_id = $1                [load-bearing,  │
                    │        AND kind = $N   (if kind given)  unchanged]  │
                    │        AND (guild_id = $M OR guild_id IS NULL)      │
                    │            (if guild_id given)      [NEW clause]   │
                    │  ORDER BY embedding <=> $2 LIMIT $last              │
                    └─────────────────────────────────────────────────────┘

  Call sites opting IN (guild_scoped=True):          Call sites staying OUT (default False):
  ┌──────────────────────────────────────┐           ┌───────────────────────────────────┐
  │ cogs/ai.py:220     /roast @user       │           │ cogs/ai.py:134      /ask (MEM-02) │
  │ cogs/events.py:163 ambient roast      │           └───────────────────────────────────┘
  │ cogs/events.py:514 proactive callback │
  │ cogs/music.py:1232 music-cmd callback │  ◀── research item 1, resolved: opt IN
  │ cogs/ai.py:336     auto-queue taste   │  ◀── research item 2, resolved: opt IN
  └──────────────────────────────────────┘

                    ┌─────────────────────────────────────────────────────┐
                    │              MemoryService.remember()               │
                    │       services/memory.py:188-342  — UNTOUCHED       │
                    │  dedup search (k=1, no guild_id, no kind) — the     │
                    │  CR-01-scarred path — zero code change (D-02)       │
                    └─────────────────────────────────────────────────────┘


  Guild-data purge (MEM-04):

  guild.leave() ──▶ discord gateway ──▶ bot.py::on_guild_remove (:762)
                                              │
                                              ├─ existing: cache-evict + owner notice [unchanged]
                                              │
                                              └─ NEW: try: await database.purge_guild_data(pool, guild_id)
                                                       except Exception: log.warning(...)  [never raises]
                                                              │
                                                              ▼
                                                 ONE transaction, 4 DELETEs:
                                                   guild_config   WHERE guild_id = $1
                                                   guild_queues   WHERE guild_id = $1
                                                   guild_jams     WHERE guild_id = $1
                                                   user_memories  WHERE guild_id = $1  (NULL rows
                                                                   excluded automatically by `=`
                                                                   semantics — D-01 corpus safe)
                                                 NEVER: guild_blocklist (Phase 20 D-01 invariant)
```

### Recommended file changes (no new files needed)

```
database.py          # search_memories() gains optional guild_id kwarg + purge_guild_data() helper
services/memory.py   # recall() gains guild_scoped: bool = False keyword-only param
cogs/ai.py           # /roast opts in; auto-queue taste-blend recall opts in
cogs/events.py       # ambient roast + proactive callback recall opt in
cogs/music.py        # _build_roast_line's recall call opts in (thread existing guild_id param through)
bot.py               # on_guild_remove calls purge_guild_data, wrapped
tests/test_memory.py, tests/test_database_phase11.py (or a new test_database_phase21.py),
tests/test_ambient_recall_cadence.py  # extended, not replaced
```

### Pattern 1: Optional-clause-omitted-entirely (Phase 14 `kind` precedent, extended to two clauses)

**What:** `database.search_memories()`'s SQL gains a second optional clause. The existing `kind`
clause hardcodes its placeholder as literal `$3` because it is always the *only* possible third
positional parameter today:

```python
# database.py:1377-1390 (CURRENT — kind is the only optional clause)
kind_clause = " AND kind = $3" if kind is not None else ""
params: list = [user_id, query_embedding] + ([kind] if kind is not None else [])
...
f" WHERE user_id = $1{kind_clause}"
" ORDER BY embedding <=> $2"
" LIMIT $" + str(len(params) + 1),
*params,
k,
```

Adding a second optional clause (guild) means the `$3` literal can no longer be hardcoded —
whichever optional clause is present alone must still bind at `$3` (byte-identical to today when
only `kind` is passed — this is asserted by `tests/test_memory.py:596-608`
`test_kind_taste_episode_appends_clause_and_binds_positionally`, which hardcodes the literal
string `"AND kind = $3"`). The fix is to compute placeholder numbers from `len(params)` at
append-time instead of a literal, and to append `kind` **before** `guild_id` so the existing
kind-only test keeps seeing `$3` for `kind`:

```python
# database.py — RECOMMENDED (dynamic numbering, order-preserving)
async def search_memories(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    query_embedding: list[float],
    k: int,
    kind: str | None = None,
    guild_id: str | None = None,   # NEW — MEM-01/D-01/D-02
) -> list[asyncpg.Record]:
    params: list = [user_id, query_embedding]
    clauses = ""
    if kind is not None:
        params.append(kind)
        clauses += f" AND kind = ${len(params)}"          # still $3 when alone (regression-safe)
    if guild_id is not None:
        params.append(guild_id)
        clauses += f" AND (guild_id = ${len(params)} OR guild_id IS NULL)"  # $3 or $4
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT id, fact, kind, salience, hit_count, created_at, last_seen_at,"
            "       last_surfaced_at, surface_count,"
            "       1 - (embedding <=> $2) AS similarity"
            " FROM user_memories"
            f" WHERE user_id = $1{clauses}"
            " ORDER BY embedding <=> $2"
            " LIMIT $" + str(len(params) + 1),
            *params,
            k,
        )
```

Verified against all four combinations:
- `kind=None, guild_id=None` → SQL identical to pre-Phase-21 output, params `(user_id, embedding, k)` — passes `tests/test_memory.py:581-594` unmodified.
- `kind="X", guild_id=None` → `AND kind = $3` — passes `tests/test_memory.py:596-608` unmodified.
- `kind=None, guild_id="G"` → `AND (guild_id = $3 OR guild_id IS NULL)` — new test needed.
- `kind="X", guild_id="G"` → `AND kind = $3 AND (guild_id = $4 OR guild_id IS NULL)` — new test needed (this is the auto-queue taste-blend call shape: `kind="taste_episode"` + `guild_scoped=True`).

**When to use:** Any time a second optional SQL filter is added to a query that already has one —
this dynamic-numbering pattern generalizes past this phase.

### Pattern 2: Keyword-only opt-in flag on `recall()`, never inferred from `guild_id` presence

**What:** `recall()`'s existing signature is `recall(self, user_id, guild_id, query_text, kind=None)`
— `guild_id` is a **required positional** parameter today (docstring: "reserved for future
per-guild memory scoping"), and every existing call site already passes a real, non-empty guild id
string (including `/ask`, which must stay global). This means **the presence of a non-null
`guild_id` argument cannot be the scoping signal** — `/ask` has one too. The fix is a new
**keyword-only** boolean appended at the end of the signature, defaulting to `False`:

```python
# services/memory.py — RECOMMENDED
async def recall(
    self,
    user_id: str,
    guild_id: str,
    query_text: str,
    kind: str | None = None,
    *,
    guild_scoped: bool = False,   # NEW — MEM-01 opt-in, D-02
) -> list[str]:
    ...
    rows = await database.search_memories(
        self._pool,
        user_id=user_id,
        query_embedding=query_vec,
        k=config.MEMORY_TOP_K,
        kind=kind,
        guild_id=guild_id if guild_scoped else None,   # omitted-effect when False
    )
```

Because `search_memories`'s `guild_id` parameter itself defaults to `None` and only contributes a
clause when not-`None`, passing `guild_id=None` when `guild_scoped=False` produces **exactly**
today's SQL and params tuple — no new keyword is silently threaded through with an unexpected
value. This satisfies the "byte-identical for non-opting callers" requirement precisely, and does
so without touching `remember()`'s call to `search_memories` at all (it never passes `guild_id=`,
so it is unaffected by the new parameter's *existence* — Python allows adding a new keyword-only
parameter with a default without breaking existing callers who omit it).

**Existing-test impact:** All five `svc.recall(...)` positional-call-style tests in
`tests/test_memory.py` (lines 428, 442, 482, 529, 638, 661) and the four in
`tests/test_ambient_recall_cadence.py` (which only assert on `call_args[0]`, the positional args)
remain green, because `guild_scoped` is keyword-only and defaults `False` — no test currently
passes it, so no test observes a behavior change.

**Rejected alternative — dedicated `scope_guild_id: str | None` parameter:** functionally
equivalent but redundant, since `recall()` already has a `guild_id` positional argument holding
the same value every opting-in caller would pass. A second guild-id parameter invites a
"which one do I pass" footgun (they could disagree). The boolean flag reuses the value already on
hand.

### Pattern 3: The real opt-in test is "ambient/unprompted broadcast" not "self vs. third party"

**What:** Tracing every MEM-01-named surface's actual `user_id` argument to `recall()` shows all
of them except `/roast @user` recall the **same** user who triggered the event:

| Call site | `recall()`'s `user_id` arg | Who sees the output | Requested by whom |
|---|---|---|---|
| `cogs/ai.py:134` `/ask` | `interaction.user.id` (invoker) | Whoever's in the channel | The invoker, explicitly, this instant |
| `cogs/ai.py:220` `/roast @user` | `target.id` (**not** the invoker) | Whoever's in the channel | The invoker, about someone else |
| `cogs/events.py:163` ambient roast | `member.id` (the person who just joined voice — **self**) | The whole ambient channel | Nobody — system-decided, cadence-gated |
| `cogs/events.py:514` proactive callback | `user_id` = `message.author.id` (**self**) | Reply to that same message | Nobody — system-decided, cadence-gated |
| `cogs/music.py:1232` music-cmd callback | `user_id` param, always called with `interaction.user.id` (**self** — verified at call sites `music.py:1311/1347/1384`) | The whole ambient channel (`_post_music_roast`) | Nobody — cadence-gated on a repeat-song/milestone/streak event |
| `cogs/ai.py:336` auto-queue taste blend | Each in-voice **non-bot member**'s id (genuinely other people, not any single "invoker" — auto-queue has no invoker) | Influences songs played to the whole voice channel | Nobody — queue-empty triggered |

`/ask` and `/roast` are the only two surfaces with a synchronous, explicit invoker; the other four
are all cadence-gated ambient broadcasts triggered by the system, not a user action. **The
discriminator MEM-01 actually encodes is: does a specific person explicitly, synchronously pull
their own memory (safe — stays global, MEM-02), or does the bot unpromptedly broadcast someone's
memory to a channel (unsafe across guild boundaries — scope it)?** `/roast @user`'s "third party"
framing generalizes to the ambient surfaces because in an ambient broadcast, *everyone in the
channel* is effectively a third party relative to the memory being surfaced — they didn't ask for
it and may not share the guild context the memory was formed in.

**Anti-pattern to avoid:** Do not write `guild_scoped = (user_id != invoker_id)` or any check
keyed on "is this a different user" — `cogs/music.py:1232` and the two `events.py` sites would all
incorrectly evaluate to "self, don't scope" under that rule, which is the wrong answer (see
research-item resolutions below).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Deleting a guild's persisted queue row | A new raw `DELETE FROM guild_queues` inline in the purge | The **already-existing** `QueuePersistenceService.clear_persisted(guild_id)` (`services/queue_persistence.py:70-83`) does exactly `DELETE FROM guild_queues WHERE guild_id = $1`, already wrapped in its own try/except | It is the proven, tested idiom for this exact table; reusing it (or mirroring its one-line SQL inside a new `database.purge_guild_data` transaction) avoids a second, possibly-diverging implementation of the same DELETE |
| A per-user "which guild owns this memory" derivation | Any heuristic backfill/migration for NULL `guild_id` rows | D-01's grandfather rule (`guild_id IS NULL` recalls everywhere) — already user-locked | `daily_batch` memories have no single attributable guild; a backfill would guess wrong. This is a named descope tripwire in REQUIREMENTS.md and it does not fire because the honest answer (grandfather) already exists |
| A new `logic/` pure-predicate module for "should this call site scope" | `logic/memory_scope.py` with a `decide_guild_scope(...)` function | A plain `guild_scoped=True` literal at each of the 5 opt-in call sites | The decision is a **per-call-site constant**, not runtime-computed business logic with branches — there is nothing to unit-test independently of the call site itself (see Validation Architecture). Phase 10 D-02's "logic dispatches on a returned value, glue doesn't re-derive it" principle is about avoiding *duplicated* branching logic; a static `True`/`False` literal has no branch to duplicate |

**Key insight:** Every piece of this phase already has an existing, tested idiom to mirror
(`kind`-clause optional-SQL pattern, `delete_blocklist`/`delete_all_user_memories`/`delete_jam`
DELETE-helper shape, `log_track_batch`'s single-transaction multi-DELETE precedent,
`clear_persisted`'s exact guild_queues DELETE). This phase should produce almost no genuinely novel
code shape — it recombines proven pieces.

## Research Item Resolutions (CONTEXT-flagged, decided per MEM-01's letter)

### 1. `cogs/music.py:1232` — the music-command memory callback

**Current code** (`cogs/music.py:1223-1238`):
```python
music_memories: list[str] = []
if random.random() < config.MEMORY_CALLBACK_CHANCE:
    _memory_svc = getattr(self.bot, "memory_service", None)
    if _memory_svc is not None:
        try:
            music_memories = await _memory_svc.recall(
                user_id,
                "",  # guild_id reserved — ANN scopes to user_id only
                scenario_content,
            )
```

**Decision: opt in (`guild_scoped=True`).** This is structurally identical to
`_generate_ambient_roast`'s internal recall block (`cogs/events.py:145-169`) — same
`MEMORY_CALLBACK_CHANCE` cadence gate, same "recall the subject of the roast, inject into a
Gemini prompt, post publicly via `_post_music_roast`" shape. It is an ambient/unprompted
broadcast fired on repeat-song/milestone/streak events, not an explicit user pull. All three call
sites of `_build_roast_line` (`music.py:1310`, `:1346`, `:1383`) already pass a real
`guild_id=str(interaction.guild.id)` keyword argument into `_build_roast_line` itself (used
today only for the outer `gemini_service.chat(..., guild_id=guild_id)` RATE-01 tagging call at
`music.py:1251`) — the fix threads that **already-available, already-correct** value into the
recall call instead of the placeholder `""`, and sets `guild_scoped=True`:

```python
music_memories = await _memory_svc.recall(
    user_id,
    guild_id or "",   # existing _build_roast_line param, now actually used
    scenario_content,
    guild_scoped=bool(guild_id),
)
```

(`guild_id or ""` / `guild_scoped=bool(guild_id)` handles the theoretical case where
`_build_roast_line` is ever called without a `guild_id` — none of the three current call sites do
this, but the param has a `None` default, so this guards against silently passing `guild_scoped=True`
with an empty-string guild id.)

**Test impact:** `tests/test_ambient_recall_cadence.py:37-42`
(`test_ambient_surfaces_retain_gate`) only asserts `"MEMORY_CALLBACK_CHANCE" in music_src` — still
true, unaffected.

### 2. Auto-queue positive-taste-blend recall (`cogs/ai.py:330-349`)

**Current code:** for each non-bot member currently in the guild's voice channel, calls
`_memory_svc.recall(str(_member.id), str(guild.id), _AUTO_QUEUE_TASTE_ANCHOR, kind="taste_episode")`
— `guild.id` is already passed today but ignored (same reserved-arg situation as everywhere else).
The results feed `select_positive_taste_context()` (`logic/taste.py`), which blends the facts into
an unattributed "the room tends to like" hint — never displayed verbatim, but it **does**
influence which songs the bot actually queues and plays audibly to the whole guild.

**Decision: opt in (`guild_scoped=True`).** Two independent justifications converge:
1. **Literal third-party reading:** the recalled memories belong to *other* voice-channel members,
   not any single invoker (auto-queue has no invoker — it fires when the queue empties). This is
   the single call site in the entire codebase where `recall()`'s `user_id` argument is
   genuinely someone other than "the person this event is about."
2. **Write-side consistency:** `taste_episode` facts are *already* guild-stamped at write time
   (`taste_distill_batch`, Phase 13 D-06/D-07, passes a real `guild_id`) — unlike `daily_batch`,
   there is no NULL-corpus concern here at all for this specific `kind`. Scoping the read is a
   correctness fix, not just a privacy one: today, a member whose voice-channel taste episodes were
   written while listening in Guild A has that Guild-A-flavored taste silently blended into Guild
   B's room recommendation the moment they join Guild B's voice channel — exactly the cross-guild
   travel MEM-01 names, just mediated through a recommendation instead of a visible roast line.

```python
facts = await _memory_svc.recall(
    str(_member.id),
    str(guild.id),
    _AUTO_QUEUE_TASTE_ANCHOR,
    kind="taste_episode",
    guild_scoped=True,
)
```

**Test impact:** `tests/test_autoqueue_wiring.py:45-48`
(`test_source_recalls_taste_episode_kind`) only asserts substring presence of `"recall("` and
`'kind="taste_episode"'` in the source — both remain true; no assertion breaks.

## Purge Helper (MEM-04)

### Exact shape

Following the `delete_blocklist` (`database.py:725-735`) idiom for a scoped delete, and
`log_track_batch` (`database.py:249-298`) for the single-transaction multi-statement precedent:

```python
# database.py — NEW, near the other Phase 11/20 guild-scoped helpers
async def purge_guild_data(pool: asyncpg.Pool, *, guild_id: str) -> dict[str, int]:
    """Hard-delete a departed guild's data across 4 tables in ONE transaction (MEM-04).

    NEVER touches guild_blocklist (Phase 20 D-01) — a blocked guild's block must
    outlive this purge (OWNER-04). guild_id = $1 on user_memories naturally
    excludes the grandfathered NULL corpus (D-01) — SQL equality never matches
    NULL, so no extra `AND guild_id IS NOT NULL` clause is needed.

    Called from bot.py::on_guild_remove, wrapped in try/except there so a purge
    failure can never crash guild removal (mirrors the on_guild_join WR-04
    try/except discipline).
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            r1 = await conn.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)
            r2 = await conn.execute("DELETE FROM guild_queues WHERE guild_id = $1", guild_id)
            r3 = await conn.execute("DELETE FROM guild_jams WHERE guild_id = $1", guild_id)
            r4 = await conn.execute("DELETE FROM user_memories WHERE guild_id = $1", guild_id)
    return {
        "guild_config": int(r1.split()[-1]),
        "guild_queues": int(r2.split()[-1]),
        "guild_jams": int(r3.split()[-1]),
        "user_memories": int(r4.split()[-1]),
    }
```

**Transaction vs. sequential:** recommend **one transaction** wrapping all four DELETEs (mirrors
`log_track_batch`). There are no `REFERENCES`/FK constraints anywhere in `SCHEMA_SQL` — confirmed
by reading the full schema (`database.py:1-232`) — so ordering among the four tables is
functionally irrelevant; the transaction buys atomicity (all rows for the guild vanish together
or not at all) at zero extra complexity, not correctness the sequential form would lack.

**Hook wiring** (`bot.py::on_guild_remove`, currently `:762-773`):
```python
@bot.event
async def on_guild_remove(guild: discord.Guild) -> None:
    if hasattr(bot, "guild_config"):
        bot.guild_config._cache.pop(str(guild.id), None)
    if hasattr(bot, "pool"):
        try:
            await database.purge_guild_data(bot.pool, guild_id=str(guild.id))
        except Exception as exc:
            log.warning("on_guild_remove: purge_guild_data failed for guild %s: %s", guild.id, exc)
    if hasattr(bot, "log_to_discord"):
        await bot.log_to_discord(_build_guild_notice_embed(guild, joined=False, welcome_posted=None))
```

### Confirmed: the `/guilds block` ordering hazard is safe

Read `cogs/ops.py::guilds_block` (`:571-602`) and `services/guild_config.py::block_guild`
(`:126-134`) directly. `block_guild` calls **only** `database.insert_blocklist` (writes
`guild_blocklist`) and mutates the in-memory `self._blocked` set — it never touches `guild_config`,
`guild_queues`, `guild_jams`, or `user_memories`. Since `guild.leave()` (called inside
`_force_leave_teardown`, `:520-541`) triggers `on_guild_remove` asynchronously via the gateway
(not synchronously as part of the `leave()` coroutine returning), the purge and the subsequent
`block_guild` call in `guilds_block` **can** run concurrently — but because they operate on
**completely disjoint tables** (purge: `guild_config`/`guild_queues`/`guild_jams`/`user_memories`;
block: `guild_blocklist` only), there is no read/write race, no lock contention, and no ordering
requirement between them. The CONTEXT's "ordering note (verify at plan time)" is confirmed safe by
direct code inspection — the planner does not need to add any synchronization.

### Confirmed: zero existing tests touch `on_guild_remove` / `on_guild_join`

`grep` across `tests/` for both event names returns no matches. This matches
`.planning/codebase/TESTING.md`'s stated convention: "cogs/bot.py event handlers ... Not Tested
(Discord-specific)." The purge **helper function** (`database.purge_guild_data`) should get a
mock-free live-DB test (see Validation Architecture); the **hook wiring** in `bot.py` stays
untested-by-design, consistent with every other Discord event handler in this codebase.

## Common Pitfalls

### Pitfall 1: Hardcoding `$3` for the `kind` clause breaks when a second optional clause is added

**What goes wrong:** If the guild clause is bolted on with its own hardcoded `$3` or `$4` literal
instead of computing the placeholder number from `len(params)` at append time, either (a) both
optional params collide on the same placeholder number when both are present, or (b) the
guild-only case (no `kind`) emits `$4` when it should be `$3`, breaking the existing
`test_kind_taste_episode_appends_clause_and_binds_positionally` assertion the moment `kind` is
also passed with a shifted number.
**Why it happens:** The existing code (`database.py:1377`) was written when only one optional
clause existed, so a literal was "good enough" at the time.
**How to avoid:** Append to `params` and compute the placeholder from `len(params)` at that exact
point (Pattern 1 above). Append `kind` before `guild_id` so the pre-existing kind-only test's
hardcoded `"AND kind = $3"` string keeps matching exactly.
**Warning signs:** Any new test combining `kind=` and `guild_id=` together should assert both
`"AND kind = $3"` and `"guild_id = $4"` in the same SQL string — if either shifts, the numbering
logic broke.

### Pitfall 2: Passing the new keyword unconditionally (even as `None`) into a test double that doesn't accept it

**What goes wrong:** Several existing test doubles monkeypatch `database.search_memories` with a
hand-written `async def fake_search(pool, *, user_id, query_embedding, k, kind=None):` (no
`guild_id` parameter at all — see `tests/test_memory.py:471`, `:518`,
`tests/test_memory_taste.py:156`). If `MemoryService.recall()` or `.remember()` is changed to
**always** pass `guild_id=...` to `database.search_memories` (even `guild_id=None` when not
opted in), every one of these stubs raises `TypeError: unexpected keyword argument 'guild_id'`.
**Why it happens:** It is tempting to "always thread the new param through with a default" for
symmetry with `kind`. But `kind` itself is *already* always passed by `recall()` — the existing
stubs were written/updated (Phase 14) to accept `kind=None`. A **new, third-round** change adding
`guild_id` unconditionally would require updating *every* existing stub a second time, expanding
the regression surface exactly where MEM-05 says not to.
**How to avoid:** Only `recall()`'s **own** call to `search_memories` needs `guild_id=` at all
(computed as `guild_id if guild_scoped else None`) — this is a single call site, easy to get right.
`remember()`'s call to `search_memories` (`services/memory.py:249-254`, the CR-01-scarred dedup
search) is **not touched** — it continues to omit `guild_id` (and `kind`) entirely, so its test
doubles never see the new parameter and never need updating.
**Warning signs:** If a plan task touches `services/memory.py:249-254` (the `remember()` dedup
search) at all, that is a direct violation of D-02 and should be flagged in review.

### Pitfall 3: Confusing "third party" with "different user_id"

**What goes wrong:** A planner or implementer reads MEM-01's "a third party's memories never
travel between servers" and concludes the opt-in signal should be `user_id != invoker_id`. Under
that rule, the two `cogs/events.py` ambient surfaces and the `cogs/music.py` callback (all of
which recall the **same** user the event is about, not some other party) would incorrectly be
judged "safe, no scoping needed" — exactly backwards, since MEM-01 explicitly names ambient roasts
and proactive callbacks as surfaces that DO need scoping.
**Why it happens:** The word "third party" in the requirement is written from the audience's
perspective (an ambient channel's members, relative to a memory formed in a different guild
context), not from a same-process user-id-equality check.
**How to avoid:** Use the "explicit synchronous self-pull vs. unprompted ambient broadcast" test
(Architecture Pattern 3) — it correctly classifies all six recall call sites and cleanly resolves
both CONTEXT research items without ambiguity.

## Code Examples

### Existing optional-clause precedent (verified, to be extended not replaced)

```python
# Source: database.py:1377-1378 (the exact discipline this phase's guild clause mirrors)
kind_clause = " AND kind = $3" if kind is not None else ""
params: list = [user_id, query_embedding] + ([kind] if kind is not None else [])
```

### Existing purge-adjacent DELETE idiom (mirrored, not duplicated)

```python
# Source: services/queue_persistence.py:70-83 — already does the guild_queues half of MEM-04
async def clear_persisted(self, guild_id: int) -> None:
    try:
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM guild_queues WHERE guild_id = $1", str(guild_id))
    except Exception as exc:
        log.warning("clear_persisted failed for guild %s: %s", guild_id, exc)
```

### Existing single-transaction multi-DELETE precedent

```python
# Source: database.py:267-298 (log_track_batch) — the transaction shape purge_guild_data mirrors
async with pool.acquire() as conn:
    async with conn.transaction():
        await conn.execute(...)
        await conn.execute(...)
        await conn.execute(...)
```

## State of the Art

Not applicable in the traditional sense (no external library API drift to track) — this section
documents the one **intra-codebase** state change:

| Old Approach | Current/New Approach | When Changed | Impact |
|--------------|----------------------|---------------|--------|
| `recall()`'s `guild_id` positional param accepted but fully ignored (docstring: "reserved for future scoping") | `recall()` gains a keyword-only `guild_scoped: bool` that, when `True`, actually uses the existing `guild_id` value to narrow the ANN search | This phase (21) | The "reserved for future" comment in `services/memory.py:88-91` becomes stale and should be updated/removed as part of this phase's tasks |
| `on_guild_remove` does cache-evict + owner-notice only, no DB write | `on_guild_remove` also purges 4 tables' worth of `guild_id = $1` rows | This phase (21) | Closes the "orphaned guild data survives forever" gap the Phase 20 D-01 docstring (`bot.py:765-768`) explicitly named as this phase's job |

**Deprecated/outdated:** The `services/memory.py:88-91` docstring line "reserved for future
per-guild memory scoping; currently the ANN scopes to user_id only" should be rewritten once
`guild_scoped` ships — leaving it as-is post-implementation would be a stale-comment regression.

## Descope Tripwires — Evaluated Against The Actual Code

The standing Descope Rule names three specific tripwires. Each is evaluated here against the real
code read during this research, not hypothetically:

1. **"The `guild_id = NULL` backward-compat rule (MEM-03) has no clean answer that preserves the
   existing memory corpus."** — **Does NOT fire.** D-01's grandfather rule
   (`(guild_id = $N OR guild_id IS NULL)`) is directly implementable as a single SQL clause with no
   ambiguity, and the scouting finding in 21-CONTEXT.md (every unprompted write surface already
   stamps a real `guild_id`; only `daily_batch` in `services/memory.py`'s `distill()` passes `None`)
   is confirmed correct by this research: `cogs/music.py` (`repeat_song`/`milestone`), `cogs/ai.py`
   (`auto_queue_ignored`), and `cogs/events.py` (ambient roast kinds) all pass a real
   `guild_id=str(...guild.id)` at their `distill_and_remember`/`remember` call sites (confirmed by
   direct grep + read of each call site during this research). The NULL corpus is narrow and known.

2. **"Guild-scoped search cannot be made safe against cross-kind dedup / `expires_at`
   corruption (MEM-05)."** — **Does NOT fire.** The new clause is confined entirely to
   `search_memories`'s **read** path via a parameter that `remember()`'s dedup search
   (`services/memory.py:249-254`) never passes. Verified directly: `remember()`'s call is
   `database.search_memories(self._pool, user_id=user_id, query_embedding=fact_vec, k=1)` — zero
   change required there, zero risk of the guild clause leaking into the CR-01-scarred
   `nearest_kind`/`refresh_memory_expiry` branch (`services/memory.py:256-285`). A regression test
   asserting this call site's source/behavior is unchanged closes the loop (see Validation
   Architecture).

3. **"The guild-data purge (MEM-04) cannot cleanly separate guild-scoped memories from
   user-scoped ones."** — **Does NOT fire.** `user_memories.guild_id` is a plain nullable TEXT
   column; `DELETE FROM user_memories WHERE guild_id = $1` is unambiguous SQL that matches exactly
   the guild-stamped rows for that guild and — by ordinary SQL three-valued-logic semantics —
   never matches `NULL` rows (equality against NULL is never true), so the D-01 grandfathered
   global corpus is automatically excluded from the purge with **no extra clause needed**. This was
   independently confirmed by re-reading the `user_memories` schema
   (`database.py:1-`, no CHECK/trigger complicates equality semantics) and is not a training-data
   assumption about SQL NULL handling — it is standard, documented Postgres behavior for the `=`
   operator.

**Conclusion: none of the three named tripwires fire. Attempt the full hybrid scoping (D-04)** —
this matches the CONTEXT's own read of the scouting findings, now confirmed against the literal
code rather than inferred.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Postgres `=` never matches `NULL` (standard SQL three-valued logic), so `WHERE guild_id = $1` on `user_memories` automatically excludes the D-01 grandfathered NULL corpus without an extra clause | Purge Helper / Descope Tripwire 3 | LOW risk — this is documented, uncontroversial ANSI SQL/Postgres behavior, not project-specific; if somehow wrong, the fix is a trivial `AND guild_id IS NOT NULL` addition with no design implication |
| A2 | discord.py's gateway fires `on_guild_remove` asynchronously (not synchronously inside the `guild.leave()` coroutine's return), making the purge-vs-blocklist-insert ordering genuinely concurrent rather than sequential | Purge Helper / ordering-hazard confirmation | LOW risk — even if gateway timing were somehow synchronous, the conclusion (no race) is unchanged because the two operations touch disjoint tables regardless of interleaving order |

**Both assumptions are LOW risk and don't change the recommended design even in the pessimistic
case** — no user confirmation is required before planning proceeds.

## Open Questions

None outstanding. Every question the CONTEXT explicitly flagged as a "research item, don't guess"
(the two recall call sites) is resolved above with code-level justification, and all three descope
tripwires are evaluated against the actual schema/code rather than left open.

## Environment Availability

Skipped — this phase has no external tool/service dependencies beyond the already-running Neon
Postgres (pgvector) the rest of the codebase already depends on, and CI already runs a
`pgvector/pgvector:pg16` service container (`.github/workflows/ci.yml`, landed Phase 18).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio |
| Config file | none — implicit defaults (`.planning/codebase/TESTING.md`) |
| Quick run command | `pytest tests/test_memory.py tests/test_ambient_recall_cadence.py tests/test_autoqueue_wiring.py -x` |
| Full suite command | `pytest` (CI: `.github/workflows/ci.yml`, pgvector service container) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|--------------------|--------------|
| MEM-02 | `/ask` recall stays invoker-scoped, un-guild-scoped, unaffected | unit (mock-free-ish, mocked memory_service) | `pytest tests/test_ambient_recall_cadence.py::test_ask_always_recalls_invoker_scoped -x` | ✅ already exists — extend to also assert `guild_scoped` not passed/False |
| MEM-01 | `/roast @user` recall passes `guild_scoped=True` | unit | new test in `tests/test_ambient_recall_cadence.py` asserting `call_args.kwargs.get("guild_scoped") is True` | ❌ Wave 0 |
| MEM-01 | ambient roast + proactive callback recall pass `guild_scoped=True` | unit | new tests, same file, patch `bot.memory_service.recall` and assert kwarg | ❌ Wave 0 |
| MEM-01 | music-command callback + auto-queue taste blend recall pass `guild_scoped=True` | unit | new tests in `tests/test_ambient_recall_cadence.py` / `tests/test_autoqueue_wiring.py` | ❌ Wave 0 |
| MEM-03 | `search_memories(guild_id="G")` emits `(guild_id = $N OR guild_id IS NULL)`, byte-identical when `guild_id=None` | unit (fake pool, source-of-truth SQL string) | `pytest tests/test_memory.py -k guild -x` (new `TestSearchMemoriesGuildFilter` class mirroring `TestSearchMemoriesKindFilter`) | ❌ Wave 0 |
| MEM-03 | live-DB: a `guild_id=NULL` row and a `guild_id="other"` row are both/neither returned correctly under scoped vs. unscoped recall | integration (live pgvector) | `pytest tests/test_database_phase11.py -k search_memories` (extend) or new `tests/test_database_phase21.py` | ❌ Wave 0 |
| MEM-05 | `remember()`'s dedup search call is unchanged (no `guild_id`/no new kwarg reaches it) | unit (source/behavior assertion) | new test in `tests/test_memory_taste.py` or a new file, reusing the `fake_search(pool, *, user_id, query_embedding, k)` no-`guild_id`-accepted stub shape already used at `tests/test_memory_taste.py:156` | ❌ Wave 0 |
| MEM-05 | D-05 `refresh_memory_expiry` self-refresh semantics (matched-row-kind gating) stay byte-identical after the guild-scoping change | unit | `pytest tests/test_memory_taste.py -k dedup` (existing tests should still pass unmodified — regression, not new coverage) | ✅ already exists, run as regression gate |
| MEM-04 | `purge_guild_data` deletes exactly the 4 named tables' `guild_id=$1` rows and never touches `guild_blocklist` | integration (live pgvector) | new `tests/test_database_phase21.py::test_purge_guild_data_deletes_four_tables_only` | ❌ Wave 0 |
| MEM-04 | `purge_guild_data` leaves `guild_id IS NULL` `user_memories` rows untouched | integration (live pgvector) | same new test file, additional assertion | ❌ Wave 0 |
| MEM-04 | `on_guild_remove` calls the purge wrapped in try/except (never crashes) | structural/manual review | N/A — Discord glue, untested-by-design per TESTING.md; verified by code review only | N/A |

### Sampling Rate

- **Per task commit:** `pytest tests/test_memory.py tests/test_ambient_recall_cadence.py tests/test_autoqueue_wiring.py tests/test_memory_taste.py -x` (fast, no live DB required for the SQL-string and mocked-recall tests)
- **Per wave merge:** full suite including live-DB tests (`pytest` — CI's pgvector container makes this actually run)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] New `TestSearchMemoriesGuildFilter` class in `tests/test_memory.py` — mirrors
      `TestSearchMemoriesKindFilter` exactly (fake-pool SQL-string assertions for all 4
      kind×guild combinations)
- [ ] New `TestRecallGuildScoped` class in `tests/test_memory.py` — mirrors `TestRecallKindParam`
      (asserts `guild_scoped` forwards correctly, defaults `False`)
- [ ] Extended assertions in `tests/test_ambient_recall_cadence.py` for `/roast`, ambient roast,
      proactive callback, music-command callback — each asserting `guild_scoped=True` is passed
- [ ] New assertion in `tests/test_autoqueue_wiring.py` for `guild_scoped=True` on the taste-blend
      recall call
- [ ] New `tests/test_database_phase21.py` (or extend `test_database_phase11.py`) — live-DB tests
      for: (a) guild-scoped search returns `guild_id=NULL` + matching-guild rows, excludes
      other-guild rows; (b) `purge_guild_data` deletes the right 4 tables' rows and nothing else,
      confirmed by inserting a `guild_blocklist` row for the same guild_id first and asserting it
      survives
- [ ] New regression test locking `remember()`'s dedup search call shape (no `guild_id` kwarg ever
      reaches `database.search_memories` from that call site) — the single test MEM-05 most
      directly demands
- No new test framework/config needed — pytest + pytest-asyncio + the existing `conftest.py` pool
  fixture (pgvector-codec-registered) cover every test type this phase needs.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | no | No new auth surface — recall scoping and purge both operate on data already scoped by Discord's own guild/user identity, unchanged this phase |
| V3 Session Management | no | No session state introduced |
| V4 Access Control | **yes** | This phase *is* an access-control fix: the guild clause is a tenant-isolation boundary (`WHERE user_id = $1` remains the load-bearing cross-user guard per T-11-03a; the new `AND (guild_id = $N OR guild_id IS NULL)` narrows *within* that scope, never widens it — verified: the clause is always `AND`-appended, never `OR`-appended to the outer WHERE) |
| V5 Input Validation | no | `guild_id` values passed to `search_memories`/`purge_guild_data` originate from `discord.Guild.id` (an int cast to str), never from user-supplied text — no new untrusted-input surface |
| V6 Cryptography | no | No new cryptographic surface |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| A guild-scoped clause implemented as the *only* WHERE filter (dropping `user_id = $1`) | Information Disclosure (cross-user, far worse than cross-guild) | The guild clause is additive-only (`AND`), appended after the existing `user_id = $1` filter, never replacing it — verified in Pattern 1's SQL shape above; a regression test should assert `"user_id = $1"` remains present in every guild-scoped SQL output |
| A degenerate `guild_id IS NULL`-only clause (forgetting the `OR guild_id = $N` half) | Information Disclosure (silently blinds all guild-scoped recall to nothing, defeating MEM-01) | Exact clause text is `(guild_id = $N OR guild_id IS NULL)` as a single parenthesized OR-group, per D-01 — a new test should assert both branches are present in the SQL string, not just one |
| `purge_guild_data` accidentally deleting `guild_blocklist` rows (e.g. a future refactor adding "just delete everything with this guild_id" across all tables via a loop) | Tampering / Denial of the abuse-mitigation control (OWNER-04 regression) | The table list is an explicit, hardcoded list of exactly 4 table names in `purge_guild_data` — never a dynamic "all tables with a guild_id column" introspection. A dedicated live-DB test inserts a `guild_blocklist` row for the target guild_id before calling `purge_guild_data` and asserts it still exists afterward |
| Guild-scoped read silently regressing to global (accidentally always passing `guild_scoped=True` or always `False` due to a copy-paste default) | Information Disclosure / functional regression | The keyword-only-with-explicit-True-at-each-opt-in-site pattern makes every scoped call site visually distinct (`guild_scoped=True` literal) from the one global call site (`/ask`, no kwarg at all) — a source-inspection test per call site (mirroring `test_ambient_recall_cadence.py`'s existing style) locks this |

## Sources

### Primary (HIGH confidence — direct codebase reads, this session)
- `services/memory.py` (full file, 539 lines) — `recall`/`remember`/`distill`/`distill_and_remember`/`sweep`
- `database.py` — `search_memories` (:1333-1390), `insert_memory` (:1393-1441), `bump_memory_hit`
  (:1444-1466), `refresh_memory_expiry` (:1469-1492), `delete_all_user_memories` (:1624-1647),
  `delete_blocklist`/`insert_blocklist` (:704-735), `delete_jam` (:1292-1312), `SCHEMA_SQL`
  (:1-232), `log_track_batch` (:249-298)
- `bot.py` — `on_guild_join` (:707-758), `on_guild_remove` (:761-773)
- `cogs/ai.py` — `/ask` (:105-175), `/roast` (:179-263), `try_auto_queue` (:267-448)
- `cogs/events.py` — `_generate_ambient_roast` (:97-207), voice-join dispatch (:211-329),
  `_maybe_fire_proactive_callback` region (:460-530)
- `cogs/music.py` — `_build_roast_line` (:1182-1266), `_log_track` call sites (:1268-1391+)
- `cogs/ops.py` — `_force_leave_teardown` (:520-541), `guilds_leave`/`guilds_block`/`guilds_unblock`
  (:543-621)
- `services/guild_config.py` — `block_guild`/`unblock_guild`/`is_blocked` (:126-143)
- `services/queue_persistence.py` — `clear_persisted` (:70-83)
- `tests/test_memory.py` (full `TestRecallService`, `TestSearchMemoriesKindFilter`,
  `TestRecallKindParam` classes)
- `tests/test_memory_taste.py` (dedup/refresh monkeypatch tests, lines 140-240)
- `tests/test_ambient_recall_cadence.py` (full file)
- `tests/test_autoqueue_wiring.py` (full file)
- `tests/conftest.py` (:1-60, pool fixture + pgvector codec registration)
- `requirements.txt` (:1,3,14 — discord.py/asyncpg/pgvector versions)
- `.planning/phases/21-memory-scoping-guild-data-lifecycle/21-CONTEXT.md` (full, including
  `<canonical_refs>` and `<code_context>`)
- `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md` (Phase 21 sections), `.planning/STATE.md`
- `.planning/codebase/TESTING.md`
- `.planning/config.json` (confirms `nyquist_validation`/`security_enforcement` keys absent → both default-enabled)
- `.planning/phases/20-owner-control-plane-rate-observability/20-RESEARCH.md` (format precedent for Security Domain section)

### Secondary (MEDIUM confidence)
None needed — every claim in this document is a direct read of this repository's own code or
tests; there was no library-API question requiring Context7/WebSearch verification (zero new
dependencies).

### Tertiary (LOW confidence)
None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies, all versions read directly from `requirements.txt`
- Architecture: HIGH — every pattern is either read directly from existing code or is a minimal,
  precedent-mirroring extension of one (Phase 14 kind-clause pattern, `log_track_batch` transaction
  shape, `clear_persisted` DELETE shape)
- Pitfalls: HIGH — both pitfalls were discovered by directly reading existing test-double
  signatures (`tests/test_memory.py`, `tests/test_memory_taste.py`) and reasoning about exactly
  what breaks them, not by speculation
- Descope tripwire evaluation: HIGH — each tripwire was checked against the literal schema/code
  (SQL NULL semantics, actual write-site `guild_id` values, actual table list), not asserted from
  memory

**Research date:** 2026-07-14
**Valid until:** Stable — this is intra-codebase surgery with zero external dependencies; no
freshness decay expected. Re-verify only if Phase 22/23 touch `services/memory.py`,
`database.py::search_memories`, or `bot.py::on_guild_remove` before Phase 21 executes.
