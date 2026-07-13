# Phase 21: Memory Scoping & Guild Data Lifecycle - Pattern Map

**Mapped:** 2026-07-14
**Files analyzed:** 8 modified (0 new files — this phase is pure in-place surgery)
**Analogs found:** 8 / 8 (all analogs are in the SAME files being modified — this is a
same-file-precedent phase, not a cross-file-borrow phase)

## File Classification

| Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `database.py::search_memories` (:1333) | service/query helper | CRUD (read, ANN) | Same function's existing `kind` clause (Phase 14) | exact — self-analog |
| `database.py::purge_guild_data` (new helper) | service/query helper | batch (transactional multi-DELETE) | `database.py::log_track_batch` (:249) + `delete_blocklist` (:725) + `delete_all_user_memories` (:1624) + `guild_jams` delete (:1306) | exact — composite of 4 existing idioms |
| `services/memory.py::recall` (:60) | service | request-response (read) | Same function's existing `kind` param (Phase 14 thread-through) | exact — self-analog |
| `bot.py::on_guild_remove` (:762) | event handler (Discord glue) | event-driven | `bot.py::on_guild_join` (:707) WR-04 try/except discipline | exact — sibling handler in same file |
| `cogs/ai.py` (`/ask` :134, `/roast` :220, auto-queue :336) | controller / service glue | request-response + event-driven | Each site's own current `recall()` call (below) | exact — self-analog per site |
| `cogs/events.py` (ambient roast :163, proactive :514) | event handler glue | event-driven | Each site's own current `recall()` call (below) | exact — self-analog per site |
| `cogs/music.py` (`_build_roast_line` :1232) | service glue | event-driven | Same function's current `recall()` call + `guild_id` param already threaded to `chat()` at :1251 | exact — self-analog |
| `tests/test_memory.py`, `tests/test_ambient_recall_cadence.py`, `tests/test_autoqueue_wiring.py`, new `tests/test_database_phase21.py` | test | CRUD/event assertion | `TestSearchMemoriesKindFilter`, `TestRecallKindParam`, existing ambient-cadence tests, `tests/test_memory_taste.py:156` fake_search stub | exact — direct structural templates |

## Pattern Assignments

### `database.py::search_memories` (:1333) — gains second optional clause

**Analog:** the function's own existing `kind` clause (Phase 14 precedent), same file.

**Current code** (`database.py:1377-1390`):
```python
kind_clause = " AND kind = $3" if kind is not None else ""
params: list = [user_id, query_embedding] + ([kind] if kind is not None else [])
...
f" WHERE user_id = $1{kind_clause}"
" ORDER BY embedding <=> $2"
" LIMIT $" + str(len(params) + 1),
*params,
k,
```

**Pitfall (must fix, not just extend):** `$3` is currently a **hardcoded literal**, correct only
because `kind` is today the sole optional clause. Adding `guild_id` as a second optional clause
without switching to dynamic numbering causes either a placeholder collision (both optional
params landing on `$3`) or a shifted-by-one break in the existing
`test_kind_taste_episode_appends_clause_and_binds_positionally` assertion the moment both are
present together.

**Correct form (dynamic numbering, order-preserving — append `kind` before `guild_id` so the
existing kind-only test keeps seeing literal `$3`):**
```python
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
        clauses += f" AND kind = ${len(params)}"                       # still $3 when alone
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

**Four combinations to test (from RESEARCH):**
- `kind=None, guild_id=None` → byte-identical to today.
- `kind="X", guild_id=None` → `AND kind = $3` (existing test, unmodified).
- `kind=None, guild_id="G"` → `AND (guild_id = $3 OR guild_id IS NULL)` (new).
- `kind="X", guild_id="G"` → `AND kind = $3 AND (guild_id = $4 OR guild_id IS NULL)` (new — this
  is the exact shape the auto-queue taste-blend call produces).

**Invariant to lock in a test:** `WHERE user_id = $1` must remain present verbatim in every
guild-scoped SQL output (V4 access-control regression: the guild clause narrows *within*
`user_id = $1`, never replaces or OR-widens it).

---

### `database.py::purge_guild_data` (new helper) — MEM-04

**Analogs:** `delete_blocklist` (:725) for the scoped-delete shape, `log_track_batch` (:249) for
the single-transaction multi-statement shape, `services/queue_persistence.py::clear_persisted`
(:70) for the exact `guild_queues` DELETE this purge must reproduce (or could call directly),
`delete_jam` (:1306) for a name/guild-scoped delete precedent.

**`clear_persisted` (the exact `guild_queues` half, already tested/proven):**
```python
# services/queue_persistence.py:70-83
async def clear_persisted(self, guild_id: int) -> None:
    try:
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM guild_queues WHERE guild_id = $1", str(guild_id))
    except Exception as exc:
        log.warning("clear_persisted failed for guild %s: %s", guild_id, exc)
```

**`log_track_batch` transaction shape (single-transaction multi-DELETE precedent):**
```python
# database.py:267-298 pattern
async with pool.acquire() as conn:
    async with conn.transaction():
        await conn.execute(...)
        await conn.execute(...)
        await conn.execute(...)
```

**Recommended new helper (verbatim from RESEARCH, verified against schema — no FK constraints
anywhere in `SCHEMA_SQL`, so table order within the transaction is irrelevant):**
```python
async def purge_guild_data(pool: asyncpg.Pool, *, guild_id: str) -> dict[str, int]:
    """Hard-delete a departed guild's data across 4 tables in ONE transaction (MEM-04).

    NEVER touches guild_blocklist (Phase 20 D-01) — a blocked guild's block must
    outlive this purge (OWNER-04). guild_id = $1 on user_memories naturally
    excludes the grandfathered NULL corpus (D-01) — SQL equality never matches
    NULL, so no extra `AND guild_id IS NOT NULL` clause is needed.
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

**Hard invariant:** table list is an explicit, hardcoded 4-name list — never a dynamic
"introspect all tables with a `guild_id` column" loop (that would eventually sweep up
`guild_blocklist`). A live-DB test must insert a `guild_blocklist` row for the same `guild_id`
first and assert it **survives** the purge call.

---

### `services/memory.py::recall` (:60) — gains explicit guild-scoping opt-in

**Analog:** the same function's existing `kind: str | None = None` param, threaded through from
Phase 14 — same thread-through shape, new keyword-only boolean instead.

**Current signature area (per RESEARCH, `:60`-ish):**
```python
async def recall(
    self,
    user_id: str,
    guild_id: str,      # accepted but IGNORED today — docstring: "reserved for future scoping"
    query_text: str,
    kind: str | None = None,
) -> list[str]:
    ...
```

**Correct new form (keyword-only, defaults False — do NOT infer scoping from `guild_id`'s mere
presence; both `/roast` and `/ask` pass a real non-null `guild_id` today):**
```python
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

**Critical DO-NOT-TOUCH (D-02 / MEM-05 / CR-01 scar):** `remember()`'s own call to
`search_memories` (the k=1 dedup search, `services/memory.py:249-254`) is a **separate call
site** and must NOT gain a `guild_id=` kwarg at all — it must remain exactly:
```python
database.search_memories(self._pool, user_id=user_id, query_embedding=fact_vec, k=1)
```
Any plan task touching `services/memory.py:249-254` is a direct D-02 violation and should be
flagged in review. This is the single test double compatibility hazard: `tests/test_memory.py:471,
:518` and `tests/test_memory_taste.py:156` monkeypatch `search_memories` with hand-written stubs
that do **not** accept a `guild_id` kwarg — if `guild_id` were ever passed unconditionally
(even as `None`) from a call site those stubs intercept, every one of them raises
`TypeError: unexpected keyword argument 'guild_id'`.

**Stale docstring to update as part of this phase:** `services/memory.py:88-91`'s "reserved for
future per-guild memory scoping; currently the ANN scopes to user_id only" becomes stale once
`guild_scoped` ships and should be rewritten.

---

### `bot.py::on_guild_remove` (:762) — wire the purge call

**Analog:** `bot.py::on_guild_join` (:707-758)'s WR-04 try/except discipline, same file, sibling
handler.

**`on_guild_join`'s WR-04 excerpt (the discipline to mirror):**
```python
# bot.py:739-756
welcome_posted = False
try:
    row = await database.insert_guild_config_if_absent(bot.pool, guild_id=str(guild.id))
    if should_welcome_guild(inserted_row=row):
        bot.guild_config._refresh_cache_entry(row)
        welcome_posted = await _post_guild_welcome(guild)
    else:
        existing_row = await database.get_guild_config(bot.pool, guild_id=str(guild.id))
        if existing_row is not None:
            bot.guild_config._refresh_cache_entry(existing_row)
except Exception as exc:
    log.warning("on_guild_join: DB write/welcome chain failed for guild %s: %s", guild.id, exc)

await bot.log_to_discord(_build_guild_notice_embed(guild, joined=True, welcome_posted=welcome_posted))
```

**Current `on_guild_remove` (`bot.py:761-773`, the exact function this phase edits) — note the
docstring literally names this phase's job:**
```python
@bot.event
async def on_guild_remove(guild: discord.Guild) -> None:
    """Guild removal: notify owner + evict the cache entry only — NO DB write (D-12).

    The MEM-04 guild-data purge is Phase 21's job. Phase 21 must also preserve
    a blocked guild's row (or move the blacklist to its own table) so a
    kicked-then-re-invited guild can be refused — this plan does not solve
    that constraint, only carries it forward.
    """
    if hasattr(bot, "guild_config"):
        bot.guild_config._cache.pop(str(guild.id), None)
    if hasattr(bot, "log_to_discord"):
        await bot.log_to_discord(_build_guild_notice_embed(guild, joined=False, welcome_posted=None))
```

**Recommended edit (wrapped, non-crashing, inserted between cache-evict and owner-notice):**
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

Note: Phase 20 D-01 already moved the blocklist to its own table (`guild_blocklist`), so the
docstring's "or move the blacklist to its own table" caveat is already satisfied — the purge is
unconstrained on the 4 guild-data tables and must never reference `guild_blocklist`.

**Untested-by-design:** per `.planning/codebase/TESTING.md`, Discord event handlers are
structural/manual-review only — no unit test for the hook wiring itself, only for
`purge_guild_data` (the pure DB helper) via live-DB tests.

---

### `cogs/ai.py` — three recall call sites (one stays global, two opt in)

**`/ask` (:134) — STAYS GLOBAL (MEM-02), no code change to the call itself:**
```python
memories = await _memory_svc.recall(
    str(interaction.user.id),
    str(interaction.guild_id),
    question,  # /ask question text is the recall anchor
)
```
No `guild_scoped=` kwarg added here — this is the one call site that must remain exactly as-is.
A new/extended test should assert `guild_scoped` is absent from `call_args.kwargs` (or `False`).

**`/roast @user` (:220) — OPTS IN (MEM-01):**
Add `guild_scoped=True` to the existing call (current call shape at :220 mirrors `/ask`'s
structure with `target.id` instead of `interaction.user.id` — read exact current text before
editing, but the edit is additive: append the new kwarg).

**Auto-queue taste-blend recall (:330-349) — OPTS IN (resolved research item):**
Current code already passes `kind="taste_episode"` and an already-guild-stamped `guild.id`:
```python
facts = await _memory_svc.recall(str(_member.id), str(guild.id), _AUTO_QUEUE_TASTE_ANCHOR, kind="taste_episode")
```
Add `guild_scoped=True`:
```python
facts = await _memory_svc.recall(
    str(_member.id),
    str(guild.id),
    _AUTO_QUEUE_TASTE_ANCHOR,
    kind="taste_episode",
    guild_scoped=True,
)
```
This is the `kind="X" AND guild_id="G"` combination — the SQL shape that exercises both optional
clauses simultaneously (`AND kind = $3 AND (guild_id = $4 OR guild_id IS NULL)`).

**Test impact:** `tests/test_autoqueue_wiring.py:45-48`
(`test_source_recalls_taste_episode_kind`) only asserts substring presence of `"recall("` and
`'kind="taste_episode"'` — unaffected; add a new assertion for `guild_scoped=True`.

---

### `cogs/events.py` — ambient roast + proactive callback (both opt in, MEM-01)

**Ambient roast (:158-169), current code:**
```python
amb_memories = []
if random.random() < config.MEMORY_CALLBACK_CHANCE:
    _memory_svc = getattr(self.bot, "memory_service", None)
    if _memory_svc is not None:
        try:
            amb_memories = await _memory_svc.recall(
                str(member.id),
                str(member.guild.id),
                scenario,  # formatted scenario is the recall anchor
            )
        except Exception as _mem_err:
            log.debug("memory.recall failed (non-fatal): %s", _mem_err)
```
Edit: append `guild_scoped=True` to the `recall(...)` call.

**Proactive callback (:514), current code (one-liner, no cadence gate inline here — gate lives
in the pure `logic/proactive.py` predicate called earlier):**
```python
memories = await memory_service.recall(user_id, str(message.guild.id), anchor)
```
Edit: append `guild_scoped=True`.

**Test impact:** `tests/test_ambient_recall_cadence.py` (full file) is the existing structural
template — extend it with new assertions per call site (`call_args.kwargs.get("guild_scoped") is
True` for the three opt-in sites, `is not True` for `/ask`).

---

### `cogs/music.py::_build_roast_line` (:1223-1238) — opts in (resolved research item)

**Current code:**
```python
# scenario_content is the recall anchor; guild_id is reserved in recall()
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

**Correct edit** — thread the ALREADY-AVAILABLE `guild_id` param (used today only for the outer
`gemini_service.chat(..., guild_id=guild_id)` RATE-01 call at `music.py:1251`) into the recall
call instead of the `""` placeholder, and set `guild_scoped` conditionally so a hypothetical
future no-guild_id call site can't accidentally pass `guild_scoped=True` with an empty string:
```python
music_memories = await _memory_svc.recall(
    user_id,
    guild_id or "",   # existing _build_roast_line param, now actually used
    scenario_content,
    guild_scoped=bool(guild_id),
)
```
All three current call sites of `_build_roast_line` (`music.py:1310`, `:1346`, `:1383`) already
pass a real `guild_id=str(interaction.guild.id)` — this is not a new plumbing requirement, just a
new use of an existing value.

**Test impact:** `tests/test_ambient_recall_cadence.py:37-42`
(`test_ambient_surfaces_retain_gate`) only asserts `"MEMORY_CALLBACK_CHANCE" in music_src` —
unaffected; add a new assertion for `guild_scoped=` presence.

---

## Shared Patterns

### Optional-SQL-clause-omitted-entirely (the single pattern underlying most of this phase)
**Source:** `database.py::search_memories`'s existing `kind` clause (Phase 14), extended per above.
**Apply to:** the new `guild_id` clause in the same function. Never emit a degenerate
`guild_id IS NULL`-only clause (that would silently blind ALL guild-scoped recall — a security
regression per the RESEARCH Security Domain table). Always the full
`(guild_id = $N OR guild_id IS NULL)` OR-group, and always `AND`-appended after the load-bearing
`user_id = $1` guard, never `OR`-appended to it.

### Keyword-only opt-in flag, never inferred from an existing positional arg's presence
**Source:** `services/memory.py::recall`'s new `guild_scoped: bool = False`.
**Apply to:** every call site listed above. The anti-pattern to avoid (per RESEARCH Pitfall 3):
`guild_scoped = (user_id != invoker_id)` — this misclassifies every ambient surface (they all
recall the *same* user the event is about) as "safe, don't scope," which is backwards. The
correct discriminator is "explicit synchronous self-pull" (stays global: `/ask` only) vs.
"unprompted/ambient broadcast to a channel" (scopes: everything else, including the two
research-item sites).

### Wrapped, non-crashing lifecycle hooks (WR-04 discipline)
**Source:** `bot.py::on_guild_join`'s try/except around the DB-write/welcome chain.
**Apply to:** `on_guild_remove`'s new purge call — a purge failure must log and be swallowed,
never propagate and crash guild removal.

### Hardcoded table list, never dynamic introspection
**Source:** the purge helper's explicit 4-name `DELETE` list.
**Apply to:** any future extension of the purge — a loop over "all tables with a `guild_id`
column" would eventually and silently sweep up `guild_blocklist`, reopening OWNER-04. Keep the
list a literal, reviewable set.

## No Analog Found

None — every file this phase touches already contains its own closest analog (a sibling function,
an adjacent call site, or the function's own prior-phase precedent). This is expected for a
same-file-surgery phase with zero new files.

## Metadata

**Analog search scope:** `database.py`, `services/memory.py`, `bot.py`, `cogs/ai.py`,
`cogs/events.py`, `cogs/music.py`, `services/queue_persistence.py`, `tests/test_memory.py`,
`tests/test_memory_taste.py`, `tests/test_ambient_recall_cadence.py`,
`tests/test_autoqueue_wiring.py`, `tests/conftest.py`.
**Files scanned:** 12 (all already fully read and cited by 21-RESEARCH.md; this pass verified the
exact current call-site text for `/ask`, ambient roast, and `on_guild_join`/`on_guild_remove` via
direct `Read`/`Grep` against the live repo state).
**Pattern extraction date:** 2026-07-14
