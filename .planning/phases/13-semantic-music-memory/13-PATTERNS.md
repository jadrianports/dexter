# Phase 13: Semantic Music Memory - Pattern Map

**Mapped:** 2026-07-02
**Files analyzed:** 5 (2 new/extend loop+db, 3 confirm-only / config-only)
**Analogs found:** 5 / 5

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `bot.py::taste_distill_batch` (new `@tasks.loop`) | scheduled task | batch/event-driven | `bot.py::memory_distill_batch` (lines 808-900) | exact |
| `config.py` (new `TASTE_*` knobs + `MEMORY_SALIENCE_BASE_WEIGHTS["taste_episode"]`) | config | N/A | `config.py` Phase 11 `MEMORY_*` block (lines 160-187) | exact |
| `database.py` (new taste aggregate helper(s), e.g. `get_user_artist_activity`) | model/query-helper | CRUD (read aggregate) | `database.py::get_user_skip_rate` (lines 1224-1246) | exact |
| `services/memory.py` | service (REUSE UNCHANGED) | request-response | itself — `distill_and_remember()` / `distill()` / `remember()` | exact (no-op) |
| `models/memory.py` | model (REUSE/extend if needed) | transform | itself — `MemoryFact` + `dedup_decision`/`compute_salience` | exact (no-op likely) |

## Pattern Assignments

### `bot.py::taste_distill_batch` (scheduled task, batch)

**Analog:** `bot.py::memory_distill_batch` (lines 808-900), sibling `memory_sweep` (lines 903-932)

**Loop declaration + schedule pattern** (lines 808-809, mirrored for `memory_sweep` at 903):
```python
@tasks.loop(time=datetime.time(hour=config.MEMORY_DISTILL_BATCH_HOUR, minute=0))
async def memory_distill_batch() -> None:
    """Daily batch: ... Fires once daily at config.MEMORY_DISTILL_BATCH_HOUR UTC (default 03:00)."""
```
For the new loop, use `@tasks.loop(time=datetime.time(hour=config.TASTE_DISTILL_BATCH_HOUR, minute=0))` at a clear slot (directional ~05:00 UTC per D-06 — distinct from 02:30/03:00/04:00 existing loops).

**No-op guard pattern** (lines 823-826):
```python
memory_service = getattr(bot, "memory_service", None)
message_buffer = getattr(bot, "message_buffer", None)
if memory_service is None or message_buffer is None:
    return
```
For `taste_distill_batch`, guard on `memory_service` (and `bot.pool` if the new DB helper needs it directly rather than through a service) — same `getattr(..., None)` pattern, never assume attribute exists (partial init / GEMINI_API_KEY unset).

**Per-user fire pattern, keyed on real snowflake** (lines 843-882) — CRITICAL: this codebase learned the hard way (CR-02 comment at line 847-852) to key memory writes on the real Discord snowflake `user_id`, never a display name. The taste loop reading `song_history`/`user_artist_counts` already has `user_id` as a native column, so this is naturally satisfied — but keep the same discipline: never derive an owner key from anything user-controllable.

**Per-user try/except swallow inside the loop body** (lines 872-887):
```python
try:
    await memory_service.distill_and_remember(
        user_id=user_id,
        guild_id=None,
        raw_text=raw_text,
        kind="daily_batch",
        base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS["daily_batch"],
    )
except Exception as exc:
    log.debug(
        "memory_distill_batch: error for user=%s channel=%d: %s",
        user_id, channel_id, exc,
    )
```
For `taste_distill_batch`, the per-user call becomes:
```python
await memory_service.distill_and_remember(
    user_id=user_id,
    guild_id=guild_id,      # taste is guild-scoped listening; song_history has guild_id — carry it through, unlike daily_batch's None
    raw_text=raw_text,       # PRE-BUCKETED qualitative text only (D-02) — never raw counts
    kind="taste_episode",
    base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS["taste_episode"],
)
```
Wrap identically in a per-user try/except so one user's failure doesn't abort the batch pass (mirrors `restore_queues`'s per-guild `continue` discipline noted in CLAUDE.md gotchas).

**`.before_loop` / `.error` pair** (lines 892-900, identical shape at 924-932):
```python
@memory_distill_batch.before_loop
async def before_memory_distill_batch() -> None:
    await bot.wait_until_ready()


@memory_distill_batch.error
async def on_memory_distill_batch_error(error: Exception) -> None:
    log.error("memory_distill_batch task error: %s", error, exc_info=error)
    await _post_loop_error("memory_distill_batch", error)
```
Clone exactly for `taste_distill_batch` with renamed function/log-string.

**Registration sites (do not miss any of these three):**
1. Start-guard block near `memory_distill_batch.start()` (lines 456-460):
```python
if not memory_distill_batch.is_running():
    memory_distill_batch.start()
```
2. `_cleanup_partial_init`'s stop-list (lines 280-281) — MUST add `taste_distill_batch` to the tuple, or a botched boot leaves it firing against a torn-down pool:
```python
for _loop in (idle_check, cache_cleanup, ytdlp_update, status_rotation,
              memory_distill_batch, memory_sweep):
```
3. The docstring comment listing stopped loops (lines 265-266, 278-279) should be updated to mention the new loop for future maintainers (documentation hygiene, not functionally required but matches existing care).

---

### `config.py` (new taste knobs)

**Analog:** `config.py` Phase 11 block (lines 160-187)

**Existing shape to mirror:**
```python
# --- Phase 11: RAG Long-Term Memory ---
MEMORY_DECAY_DAYS = 90                          # tuned via 11-02 spike 2026-06-29
MEMORY_DECAY_SALIENCE_FLOOR = 0.5              # sweep threshold ...
MEMORY_DISTILL_BATCH_HOUR = 3                   # daily distill-batch hour (UTC)

MEMORY_SALIENCE_BASE_WEIGHTS: dict[str, float] = {
    "milestone":           1.0,
    "late_night":          0.7,
    "repeat_song":         0.5,
    "auto_queue_ignored":  0.4,
    "daily_batch":         0.2,
}
```
New knobs to add in a `# --- Phase 13: Semantic Music Memory ---` block placed directly after the Phase 11 block:
```python
TASTE_DECAY_DAYS = 30                # D-03: shorter half-life than MEMORY_DECAY_DAYS=90 (Pitfall 5)
TASTE_DISTILL_BATCH_HOUR = 5         # D-06: distinct UTC slot, clear of 02:30/03:00/04:00 existing loops
TASTE_LOOKBACK_DAYS = 7              # D-07: rolling recent window for obsession/new-arrival detection
TASTE_MIN_ACTIVITY_TRACKS = 5        # D-08: min tracks in window to bother distilling (skip inactive users)
```
And extend the existing dict (do NOT create a second dict):
```python
MEMORY_SALIENCE_BASE_WEIGHTS: dict[str, float] = {
    "milestone":           1.0,
    "late_night":          0.7,
    "repeat_song":         0.5,
    "auto_queue_ignored":  0.4,
    "daily_batch":         0.2,
    "taste_episode":       0.4,   # D-04: below MEMORY_DECAY_SALIENCE_FLOOR (0.5) — genuinely sweep-eligible
}
```
Note D-04's constraint: the value MUST be `< MEMORY_DECAY_SALIENCE_FLOOR` (0.5) so `taste_episode` rows are eligible for the existing sweep — 0.4 satisfies this and matches `auto_queue_ignored`'s tier.

---

### `database.py` (new taste aggregate helper)

**Analog:** `database.py::get_user_skip_rate` (lines 1224-1246) — same shape: scoped positional-param aggregate, `pool.acquire()` + `conn.fetchrow`/`fetch`, returns raw `asyncpg.Record`(s) with no business logic (min-activity threshold, banding etc. applied by the caller, not SQL).

**Exact template to clone:**
```python
async def get_user_skip_rate(
    pool: asyncpg.Pool, *, guild_id: str, user_id: str
) -> asyncpg.Record | None:
    """Return an asyncpg Record with total_plays and total_skips for a user in a guild.

    Aggregate is all-time (no date filter, D-09) and scoped to BOTH guild_id ($1)
    and user_id ($2) — preventing cross-guild and cross-user data leakage (Pitfall 6
    / T-12-02-01). fetchrow always returns a row for COUNT(*) even when no matching
    rows exist (both counters = 0), so callers can safely treat None as 0 plays.

    The min-plays floor (D-08) is applied by logic.skip_stats.compute_skip_rate in
    the caller — never here in SQL.
    All values bound as $1/$2 positional params — no string interpolation (T-12-02-03).
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT COUNT(*) AS total_plays,"
            " COUNT(*) FILTER (WHERE was_skipped = true) AS total_skips"
            " FROM song_history"
            " WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )
```
New taste helper follows the identical convention — e.g. `get_user_recent_artist_counts(pool, *, guild_id, user_id, since)` returning per-artist play counts in the lookback window (feeds D-02 pre-bucketing in the caller, NOT in SQL — SQL returns raw counts, Python buckets them into qualitative bands before any text reaches Gemini). Keep:
- All params positional (`$1`/`$2`/...), never string-interpolated.
- Docstring stating explicit guild+user scope (cross-user/cross-guild leakage guard, mirrors Pitfall 6 language).
- Pure data fetch — no banding/thresholding logic inside the SQL/helper; that belongs to the caller in `bot.py::taste_distill_batch` (or a small pure helper) per D-02's discipline of pre-bucketing BEFORE any Gemini call.
- A second helper may be needed for the "active in last N days" candidate-user query (which users to iterate) — same pattern, scoped by `guild_id` only or unscoped `DISTINCT user_id` with a date filter; check song_history has no `guild_id`-only global scan issue (index at `idx_history_guild` exists per CLAUDE.md schema, so `WHERE guild_id = $1 AND queued_at > $2` is index-friendly).

---

### `services/memory.py` (REUSE UNCHANGED — confirm signatures only)

**Analog:** itself. No new file, no modification expected.

**Exact signature the taste task will call** (lines 419-427):
```python
async def distill_and_remember(
    self,
    *,
    user_id: str,
    guild_id: str | None,
    raw_text: str,
    kind: str,
    base_salience: float,
) -> None:
```
`taste_distill_batch` calls this exactly as `memory_distill_batch` does, with `kind="taste_episode"` and `base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS["taste_episode"]`. Internally this fans out to `distill()` (LLM extraction + `is_sensitive`/`contains_number` backstop, lines 319-413) then `remember()` (embed + dedup + cap-evict, lines 183-313) — both fully kind-agnostic, zero code change required.

**CONFIRMED — the open question from CONTEXT.md (D-05 self-refresh vs dedup risk):**
`remember()`'s dedup branch (lines 244-256):
```python
if rows:
    nearest_sim = float(rows[0]["similarity"])
    nearest_id = int(rows[0]["id"])
    if dedup_decision(nearest_sim, config.MEMORY_DEDUP_THRESHOLD):
        # Near-duplicate: bump existing row, skip insert (MEM-04)
        await database.bump_memory_hit(self._pool, nearest_id)
        ...
        return
```
And `database.py::bump_memory_hit` (lines 988-1006, read directly):
```python
async def bump_memory_hit(pool: asyncpg.Pool, memory_id: int) -> None:
    """Increment hit_count and refresh last_seen_at for a near-duplicate memory.
    ...
    A small salience nudge (±0.02, clamped to 1.0) rewards frequently observed
    facts, keeping them above low-frequency facts during eviction ranking (D-07).
    """
    async with pool.acquire() as conn:
        await conn.execute(...)   # updates hit_count, last_seen_at, salience — NOT expires_at
```
**`bump_memory_hit` does NOT touch `expires_at`.** This CONFIRMS the correctness risk CONTEXT.md flagged (D-05 open question): if a still-true steady favorite re-distills to a near-duplicate fact each cycle, it will hit the dedup branch and get `bump_memory_hit`'d — `last_seen_at` refreshes but `expires_at` (set once at insert, `datetime.now(timezone.utc) + timedelta(days=config.MEMORY_DECAY_DAYS)`, line 259) does NOT reset. Under the new `TASTE_DECAY_DAYS` (~30d, shorter than general `MEMORY_DECAY_DAYS`=90d), a durable steady-favorite fact WILL age past `expires_at` and become sweep-eligible (once `salience < MEMORY_DECAY_SALIENCE_FLOOR`, which `taste_episode`'s 0.4 base already is) even while the user keeps being true to that taste — because dedup silently no-ops the write instead of refreshing the horizon.

**Planner action required:** this needs an explicit design decision — either (a) add an `expires_at` refresh to `bump_memory_hit` for taste-decay kinds (risk: touches shared code path used by all kinds, changes Phase 11 semantics), (b) add a taste-specific "touch" path in `remember()`/`distill_and_remember()` gated by `kind == "taste_episode"` that refreshes `expires_at` on dedup-hit, or (c) accept the current behavior and rely on `hit_count`/`last_seen_at` bump alone (risking Pitfall 5's "stale taste surfaced as current" in reverse — a *true* taste ages out). Flag this in the plan; do not silently assume `services/memory.py` needs zero changes for Phase 13 — verify against D-05 before finalizing "no code change" in the PLAN.md.

---

### `models/memory.py` (extend, don't fork — likely no change needed)

**Analog:** itself. `MemoryFact` dataclass + pure functions (`apply_floor`, `rerank`, `dedup_decision`, `choose_eviction`, `compute_salience`, `is_sensitive`, `contains_number`) are already fully kind-agnostic — `dedup_decision(existing_sim, threshold)` and `compute_salience(base_weight, distiller_bump=0.0)` take no `kind` parameter and need none for Phase 13's D-01 through D-04. Only touch this file if the planner resolves the D-05 dedup/expires_at question above by adding a kind-aware branch — otherwise this file is confirm-only, same as `services/memory.py`.

## Shared Patterns

### Background loop registration (three-site checklist)
**Source:** `bot.py` lines 456-460 (start-guard), 280-281 (`_cleanup_partial_init` stop-list), 265-266/278-279 (docstring)
**Apply to:** `taste_distill_batch`
A new `@tasks.loop` is not "done" until registered at all three sites — missing the stop-list site is the most consequential omission (leaves the loop firing against a torn-down pool on a botched boot retry, per the documented WR-04 rationale).

### Accuracy firewall / number-free distillation
**Source:** `services/memory.py::distill()` (`is_sensitive`/`contains_number` backstop, lines 391-407) + CONTEXT.md D-02
**Apply to:** the raw-text builder inside `taste_distill_batch` and any new `database.py` helper
Numbers must be pre-bucketed into qualitative bands ("played heavily" / "a few times" / "dropped off" / "new this week") BEFORE the raw_text reaches `distill_and_remember()` — the existing `contains_number()` gate is belt-and-suspenders, not the primary defense (D-02). New DB helpers return raw counts; the bucketing step lives in the caller (`bot.py::taste_distill_batch`), not in SQL or in `services/memory.py`.

### Config knob placement + salience-floor discipline
**Source:** `config.py` lines 160-187
**Apply to:** new `TASTE_*` knobs + `MEMORY_SALIENCE_BASE_WEIGHTS["taste_episode"]`
Extend the existing dict rather than create a parallel one; keep the new base salience below `MEMORY_DECAY_SALIENCE_FLOOR` (0.5) per D-04 so sweep eligibility works as designed (pending resolution of the D-05 dedup/expires_at gap above).

## No Analog Found

None — all five files/changes have a direct or near-direct analog already in the codebase (Phase 11 plumbing).

## Metadata

**Analog search scope:** `bot.py`, `config.py`, `database.py`, `services/memory.py`, `models/memory.py`
**Files scanned:** 5 (all read directly, no glob/grep-only sampling needed — CONTEXT.md and ARCHITECTURE.md already named exact files and line ranges)
**Pattern extraction date:** 2026-07-02
