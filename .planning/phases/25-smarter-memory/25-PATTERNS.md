# Phase 25: Smarter Memory - Pattern Map

**Mapped:** 2026-07-15
**Files analyzed:** 6 (2 new, 4 modified)
**Analogs found:** 6 / 6

This phase is pure surgery on the existing Phase 11/13/17 memory subsystem — RESEARCH.md already
resolved the design (kind-aware batch reinforcement + fire-and-forget vision distill). This map
pins the exact analog excerpts an executor should replicate byte-for-byte, with live line numbers
re-verified 2026-07-15 (some have drifted slightly from RESEARCH.md's cited numbers — the numbers
below are current).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `database.py` (+`reinforce_memory_expiry`) | database helper | CRUD (batch UPDATE) | `database.py::bump_surfaced` (batch idiom) + `refresh_memory_expiry` (expiry-only restraint) | exact (composite of two existing siblings) |
| `services/memory.py::recall` (step 7 extended) | service | request-response (read-path side effect) | itself — step 7's existing `bump_surfaced` call, extended in place | exact |
| `cogs/events.py::_maybe_fire_vision_roast` (+ memory write) | event-driven glue | event-driven / fire-and-forget | `cogs/events.py` ambient roast site (`:276-292`) — the local `create_task(distill_and_remember(...))` idiom | exact |
| `config.py` (+2 dict entries) | config | — | `taste_episode` entries in `MEMORY_SALIENCE_BASE_WEIGHTS` (`:201`) / `MEMORY_DECAY_DAYS_BY_KIND` (`:225`) | exact |
| `tests/test_database_phase25.py` (NEW) | test | integration (live-DB) | `tests/test_database_phase11.py` (`pool` fixture, `TestWriteHelpersExist` source-inspection style, `bump_surfaced`/`delete_expired_memories` round-trip) | exact |
| `tests/test_memory.py` (`TestRecallService` extended) | test | unit (mocked) | itself — `test_returns_capped_facts_when_some_clear_floor` (`:489`), the one existing test that reaches step 7 | exact |

## Pattern Assignments

### `database.py` — NEW `reinforce_memory_expiry` (database helper, CRUD)

**Analog A — batch array-binding idiom:** `bump_surfaced` (`database.py:1734-1757`)
```python
async def bump_surfaced(pool: asyncpg.Pool, ids: list[int]) -> None:
    """Mark memories as surfaced: set last_surfaced_at = now(), increment surface_count.
    ...
    Security (T-11-03d): ids is passed via the ``ANY($1)`` array binding — no
    SQL injection path. asyncpg encodes the Python list as a Postgres array.
    """
    if not ids:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE user_memories"
            " SET last_surfaced_at = now(),"
            "     surface_count = surface_count + 1"
            " WHERE id = ANY($1)",
            ids,
        )
```

**Analog B — expiry-only restraint (D-01 discipline):** `refresh_memory_expiry` (`database.py:1553-1576`)
```python
async def refresh_memory_expiry(pool: asyncpg.Pool, memory_id: int, expires_at: datetime) -> None:
    """Reset the decay horizon on an existing memory row — expires_at ONLY.
    ... does NOT touch hit_count, salience, or last_seen_at (that is
    bump_memory_hit's job), so Phase 11 decay semantics for every other kind
    stay fully untouched.

    Args:
        pool:       asyncpg connection pool.
        memory_id:  The id of the existing user_memories row to refresh ($1).
        expires_at: New UTC decay horizon, computed by the caller ($2) — never
                    computed in SQL (e.g. now() + interval), so callers control
                    the exact decay-days constant used.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE user_memories SET expires_at = $2 WHERE id = $1",
            memory_id,
            expires_at,
        )
```

**Idiom to replicate exactly (composite of A + B, RESEARCH.md's exact recommended shape):**
```python
async def reinforce_memory_expiry(pool: asyncpg.Pool, ids: list[int], expires_at: datetime) -> None:
    """Push out expires_at for a batch of surfaced facts sharing one resolved
    decay horizon (MEM-06 / D-01). Sibling to refresh_memory_expiry (same
    expiry-only restraint) but batches over multiple ids via ANY($1),
    mirroring bump_surfaced's array-binding shape. GREATEST(...) guarantees
    reinforcement can only extend, never shorten, a fact's remaining window.
    """
    if not ids:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE user_memories SET expires_at = GREATEST(expires_at, $2) WHERE id = ANY($1)",
            ids,
            expires_at,
        )
```
Place it immediately after `refresh_memory_expiry` (near `database.py:1576`), before `count_user_memories`.
Docstring style, `Args:`/security-note convention: copy the `bump_surfaced` docstring shape verbatim (module already documents SQL-injection safety per array-binding at every such helper).

**Do NOT:** modify `bump_surfaced`'s SQL/signature; do not compute `expires_at` in SQL (`now() + interval`) — every existing expiry helper computes the datetime in Python and passes it as a param (`insert_memory`, `refresh_memory_expiry` both do this).

---

### `services/memory.py::recall` step 7 (service, request-response read-path side effect)

**Analog:** itself, current step 7 (`services/memory.py:146-193`)
```python
            # Step 3 — map rows to MemoryFact dataclass
            facts: list[MemoryFact] = [
                MemoryFact(
                    id=row["id"],
                    fact=row["fact"],
                    salience=float(row["salience"]),
                    hit_count=int(row["hit_count"]),
                    created_at=row["created_at"],
                    last_seen_at=row["last_seen_at"],
                    last_surfaced_at=row["last_surfaced_at"],
                    surface_count=int(row["surface_count"]),
                    similarity=float(row["similarity"]),
                )
                for row in rows
            ]
            ...
            # Step 6 — cap to MEMORY_INJECT_CAP (1–3)
            top = ranked[: config.MEMORY_INJECT_CAP]

            # Step 7 — bump last_surfaced_at so D-05 novelty penalty applies next call
            await database.bump_surfaced(self._pool, [f.id for f in top])
```
**Confirmed:** `MemoryFact` has NO `kind` field in the current mapping — do not add one (per RESEARCH.md's explicit anti-pattern and the CONTEXT.md wrinkle resolution).

**Idiom to add (step 7a unchanged + new step 7b, verbatim from RESEARCH.md Pattern 1):**
```python
            # Step 7a — bump last_surfaced_at (UNCHANGED — byte-identical call).
            await database.bump_surfaced(self._pool, [f.id for f in top])

            # Step 7b — MEM-06: reinforce expiry, grouped by each fact's own kind (D-01/D-02).
            # kind is read from the RAW rows (not MemoryFact) via a service-local dict —
            # use .get("kind"), never row["kind"], for compatibility with existing test
            # fixtures (_DictRecord) that predate this phase and lack a "kind" key.
            kind_by_id = {row["id"]: row.get("kind") for row in rows}
            now2 = datetime.now(timezone.utc)
            groups: dict[int, list[int]] = {}  # decay_days -> [ids]
            for f in top:
                days = resolve_decay_days(
                    kind_by_id.get(f.id),
                    default_days=config.MEMORY_DECAY_DAYS,
                    kind_overrides=config.MEMORY_DECAY_DAYS_BY_KIND,
                )
                groups.setdefault(days, []).append(f.id)
            for days, ids in groups.items():
                await database.reinforce_memory_expiry(self._pool, ids, now2 + timedelta(days=days))
```
Requires importing `resolve_decay_days` from `logic.taste` (already used elsewhere for the D-05 write-path self-refresh — check current import block at top of `services/memory.py` for the existing pattern, e.g. `from logic.taste import resolve_decay_days` or module-qualified `logic.taste.resolve_decay_days`).

**Test-breakage note (Pitfall 2, MUST fix):** `tests/test_memory.py::TestRecallService::test_returns_capped_facts_when_some_clear_floor` (`~:489`) is the only existing unit test whose `above_floor` result is non-empty, so it is the only one that reaches step 7 in the real code path. It currently monkeypatches `database.bump_surfaced` — extend its monkeypatch block to also stub `database.reinforce_memory_expiry` (a no-op fake), following the exact `fake_bump` pattern already there.

---

### `cogs/events.py::_maybe_fire_vision_roast` (event-driven glue, fire-and-forget write)

**Analog:** the existing ambient-roast fire-and-forget site, `cogs/events.py:276-292`
```python
                # D-09 path 1: fire-and-forget memory write for this notable voice event.
                # Uses create_task so the event handler is never blocked (T-11-05e / 3s rule).
                # Guarded by getattr so the bot degrades gracefully when GEMINI_API_KEY unset.
                memory_service = getattr(self.bot, "memory_service", None)
                if memory_service is not None:
                    raw_text = scenario.format(name=member.display_name) if "{name}" in scenario else scenario
                    asyncio.create_task(
                        memory_service.distill_and_remember(
                            user_id=str(member.id),
                            guild_id=str(guild.id),
                            raw_text=raw_text,
                            kind=mem_kind,
                            base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS[mem_kind],
                        )
                    )
```

**Insertion point:** `cogs/events.py::_maybe_fire_vision_roast`, current lines `683-694`:
```python
        try:
            await message.reply(
                line,
                allowed_mentions=discord.AllowedMentions.none(),
                mention_author=False,
            )
        except discord.HTTPException:
            # Send failed — do not mark the cooldown (allow a future retry).
            return

        # Successful send — mark the per-user cooldown.
        self._vision_roast_cooldowns[message.author.id] = asyncio.get_event_loop().time()
```
Add the write AFTER the cooldown-mark line (end of method), gated by the same `getattr(self.bot, "memory_service", None)` guard:
```python
        # MEM-07: fire-and-forget vision memory write — only reached when line is
        # not None AND the send succeeded. distill_and_remember swallows all
        # internal errors so this can never crash the roast path.
        memory_service = getattr(self.bot, "memory_service", None)
        if memory_service is not None:
            asyncio.create_task(
                memory_service.distill_and_remember(
                    user_id=str(message.author.id),
                    guild_id=str(message.guild.id),
                    raw_text=line,
                    kind="vision_roast",
                    base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS["vision_roast"],
                )
            )
```
**Idiom to replicate:** bare `asyncio.create_task` (matches this file's own local convention at `:284`, not `cogs/ai.py`'s `make_task`), the `getattr(self.bot, "memory_service", None)` guard, `raw_text=` is the roast **line** (`line`, the string `_generate_vision_roast` returned) — never image bytes/metadata, `exempt_numbers` defaults False inside `distill_and_remember`→`distill` (full firewall, D-04 explicit — do not pass `exempt_numbers=True`).

---

### `config.py` — two additive dict entries (config)

**Analog:** the `taste_episode` entries, `config.py:195-203` and `:224-226`
```python
MEMORY_SALIENCE_BASE_WEIGHTS: dict[str, float] = {
    "milestone": 1.0,
    "late_night": 0.7,
    "repeat_song": 0.5,
    "auto_queue_ignored": 0.4,
    "daily_batch": 0.2,
    "taste_episode": 0.4,  # D-04: MUST stay < MEMORY_DECAY_SALIENCE_FLOOR (0.5) ...
}
...
MEMORY_DECAY_DAYS_BY_KIND: dict[str, int] = {
    "taste_episode": TASTE_DECAY_DAYS,
}
```
**Idiom to add:**
```python
    "vision_roast": 0.4,  # MEM-07: < MEMORY_DECAY_SALIENCE_FLOOR (0.5) — sweep-eligible, images ephemeral
```
appended inside `MEMORY_SALIENCE_BASE_WEIGHTS`, and
```python
    "vision_roast": TASTE_DECAY_DAYS,  # MEM-07: reuse the existing 30d constant — images are ephemeral
```
appended inside `MEMORY_DECAY_DAYS_BY_KIND`. Reuse `TASTE_DECAY_DAYS` (`config.py:208`) rather than a new literal — one fewer magic number, matches the CONTEXT.md rationale verbatim.

---

### `tests/test_database_phase25.py` (NEW, integration/live-DB)

**Analog:** `tests/test_database_phase11.py` (`:1-70` shown; full file is the template)
```python
_LOCAL_DEFAULT = "postgresql://dexter:dexter@localhost:5432/dexter_test"
_TEST_DSN = os.getenv("TEST_DATABASE_URL", _LOCAL_DEFAULT)
_SKIP_LIVE = os.getenv("TEST_DATABASE_URL") is None

_skip_reason = (
    "Live pgvector DB not configured — set TEST_DATABASE_URL to run ... "
    "integration tests (e.g. a pgvector-enabled Postgres such as Neon)"
)

class TestWriteHelpersExist:
    """Verify all Task N artifacts exist with the right signatures."""
    def test_insert_memory_exists(self) -> None:
        assert hasattr(database, "insert_memory"), "insert_memory must exist in database.py"
```
**Idiom to replicate:** the skip-guard pair (`_SKIP_LIVE` env check, `@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)` on live-DB tests), the `TestWriteHelpersExist` source-inspection style (`hasattr(database, "reinforce_memory_expiry")` + `inspect.signature` checks for `ANY($1)`/`GREATEST` presence via source string check, mirroring how Phase 11 asserted `RETURNING id` presence), and the `pool` fixture already provided by `tests/conftest.py` (no new fixture needed — its `DROP TABLE ... user_memories CASCADE` teardown already covers this table).

Required test cases (from RESEARCH.md's Validation Architecture, use a **sweep-eligible kind** — salience < 0.5 — per Pitfall 1, never `milestone`):
- `TestReinforceMemoryExpiryExists` — signature/source-inspection.
- `test_reinforced_fact_survives_sweep_unreinforced_does_not` — SC-1 live round-trip.
- `test_recall_does_not_mutate_salience_or_hit_count` — SC-3 byte-identical guard.
- `TestVisionRoastMemory` — SC-2 firewall round-trip (safe line → row with `kind='vision_roast'`; sensitive/number-bearing line → zero rows).

---

### `tests/test_memory.py::TestRecallService` (unit, mocked)

**Analog:** itself, `test_returns_capped_facts_when_some_clear_floor` (`~:489`) — the only existing test reaching step 7. Its current monkeypatch block stubs `database.search_memories` and `database.bump_surfaced` (following the `fake_bump` pattern at `~:474-475,521-522`).

**Idiom to replicate:** add `database.reinforce_memory_expiry = fake_reinforce` (a no-op async stub) to that same try/finally monkeypatch block — mirror `fake_bump`'s shape exactly (same signature style, same restore-in-finally discipline). Add new unit test(s) under `TestRecallService` asserting the grouping/call-once-per-distinct-decay-days behavior with a mocked `reinforce_memory_expiry`.

**Fixture gotcha to respect:** the hand-rolled `_DictRecord(dict)` row fixtures (`~:1816`) used across `TestRecallService`/`TestRecallKindParam`/`TestRecallGuildScoped` do NOT include a `"kind"` key. `_DictRecord.__getitem__` overrides bracket access (raises `KeyError` on missing `"kind"`), but `.get()` is inherited unmodified from `dict` — so the production code's `row.get("kind")` (never `row["kind"]`) is required for these fixtures to keep passing untouched.

## Shared Patterns

### Parameterized SQL / no string interpolation
**Source:** every existing `database.py` memory helper (`bump_surfaced`, `refresh_memory_expiry`, `delete_expired_memories`)
**Apply to:** `reinforce_memory_expiry` — `$1`/`$2` placeholders only, `ids` via native `ANY($1)` array binding, `expires_at` computed in Python and passed as a parameter, never `now() + interval` in SQL.

### Fire-and-forget, error-swallowing memory writes
**Source:** `cogs/events.py:284-292` (ambient), `cogs/ai.py` (`auto_queue_ignored`, uses `make_task`), `cogs/music.py` (repeat_song/milestone)
**Apply to:** the new vision write — bare `asyncio.create_task` (matches `cogs/events.py`'s own local convention), `getattr(self.bot, "memory_service", None)` guard, `distill_and_remember` already swallows all internal errors so no additional try/except is needed at the call site.

### New memory kind = new `kind` value, never a new table/column
**Source:** Phase 13 `taste_episode` (`config.py` dict entries only, `services/memory.py`/`database.py` unchanged code paths)
**Apply to:** `vision_roast` — two additive dict entries in `config.py`, zero DDL, zero schema change; `/memory view`/`/memory forget` cover it automatically via the shared table.

### Expiry-only restraint (D-05 lineage)
**Source:** `database.refresh_memory_expiry` docstring — "does NOT touch hit_count, salience, or last_seen_at"
**Apply to:** `reinforce_memory_expiry` must follow the identical restraint — this is what makes SC-3 (byte-identical for untouched kinds) structurally provable.

## No Analog Found

None — every new/modified symbol in this phase has a direct, exact in-repo analog (Phase 11/13/17 precedent). No RESEARCH.md fallback pattern was needed.

## Metadata

**Analog search scope:** `database.py`, `services/memory.py`, `models/memory.py`, `cogs/events.py`, `config.py`, `tests/test_memory.py`, `tests/test_database_phase11.py`, `logic/taste.py`
**Files scanned:** 8 (all directly read; line numbers re-verified live 2026-07-15, several drifted from RESEARCH.md's cited numbers — this file's numbers are current)
**Pattern extraction date:** 2026-07-15
