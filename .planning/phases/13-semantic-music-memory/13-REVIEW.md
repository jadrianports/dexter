---
phase: 13-semantic-music-memory
reviewed: 2026-07-02T14:08:57Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - bot.py
  - config.py
  - database.py
  - logic/taste.py
  - services/memory.py
  - tests/test_database_phase13.py
  - tests/test_memory_taste.py
  - tests/test_taste_logic.py
findings:
  critical: 1
  warning: 2
  info: 1
  total: 4
status: issues_found
---

# Phase 13: Code Review Report

**Reviewed:** 2026-07-02T14:08:57Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

Phase 13 (Semantic Music Memory) adds a pure banding/classification module (`logic/taste.py`),
three DB aggregate helpers (`database.py`), a memory-service self-refresh branch
(`services/memory.py::remember`), and a daily `@tasks.loop` (`bot.py::taste_distill_batch`).
The accuracy-firewall goal — never interpolating SQL-known counts into a stored fact — is
**upheld** for numeric counts: `summarize_taste` emits only fixed, number-free templates, so
raw counts never reach Gemini or the vector store. Cross-guild/cross-user SQL scoping is correct
and parameterized (no injection). The pure-logic seam and test coverage are solid.

However, the review surfaced one **correctness defect in the exact area flagged for scrutiny —
the D-05 `expires_at` self-refresh** — where the refresh gate keys off the *new* fact's kind but
acts on a *matched* row that may be a different (Phase 11) kind, silently violating the module's
own "Phase 11 kinds are never touched" invariant. Two robustness/quality warnings and one dead-config
info item accompany it.

## Critical Issues

### CR-01: D-05 self-refresh rewrites the `expires_at` of a *wrong-kind* Phase 11 row on a cross-kind dedup hit

**File:** `services/memory.py:251-268` (with `database.search_memories` at `database.py:930-940`)

**Issue:**
In `remember()`, the dedup branch resolves `nearest_id` from a `search_memories(k=1)` call that is
scoped to `user_id` **only** — it is *not* scoped by `kind`, and the returned row does not even carry
a `kind` column. The self-refresh is then gated on the **new** fact's kind:

```python
if kind in config.MEMORY_DECAY_DAYS_BY_KIND:   # `kind` = the NEW fact being written
    new_expires = datetime.now(timezone.utc) + timedelta(
        days=config.MEMORY_DECAY_DAYS_BY_KIND[kind]
    )
    await database.refresh_memory_expiry(self._pool, nearest_id, new_expires)  # acts on the MATCHED row
```

When a new `taste_episode` fact is a near-duplicate (`similarity >= MEMORY_DEDUP_THRESHOLD = 0.92`)
of an existing **Phase 11** memory rather than another taste row, this branch fires and rewrites that
Phase 11 row's `expires_at` to `now + TASTE_DECAY_DAYS (30)`. This is fully reachable: the nearest
neighbor to a taste fact such as `"keeps coming back to radiohead"` can easily be an existing
`daily_batch` fact like `"they keep replaying radiohead"` at cosine ≥ 0.92.

Consequences, both wrong:
- **Indefinite survival of low-value facts:** `daily_batch` (salience 0.2) and `auto_queue_ignored`
  (0.4) are *below* `MEMORY_DECAY_SALIENCE_FLOOR = 0.5`, so they are meant to age out at their 90-day
  horizon. A daily taste distill that near-dups such a row pushes its `expires_at` to `now + 30d`
  on every run, so the sweep never reaches it — defeating the Phase 11 decay guarantee.
- **Premature expiry:** a freshly-created (90-day) `daily_batch`/`auto_queue_ignored` row gets its
  horizon *shortened* to 30 days.

This directly contradicts the invariant asserted in the surrounding comment and docstring
("Phase 11 kinds ... are never touched — dedup stays byte-identical for them"). The regression test
`tests/test_memory_taste.py::TestDecayDaysByKindMapGuard` gives false confidence: it only proves no
Phase 11 *write* kind is in the override map — it never exercises a `taste_episode` write that *matches*
a Phase 11 row, which is exactly the leak path.

**Fix:** Gate the refresh on the *matched row's* kind, not the incoming kind. Return `kind` from
`search_memories` and only refresh when the matched row is itself a short-decay kind, e.g.:

```python
# in database.search_memories SELECT list, add:  kind,
...
if rows:
    nearest_sim = float(rows[0]["similarity"])
    nearest_id = int(rows[0]["id"])
    nearest_kind = rows[0]["kind"]
    if dedup_decision(nearest_sim, config.MEMORY_DEDUP_THRESHOLD):
        await database.bump_memory_hit(self._pool, nearest_id)
        # Only refresh when the EXISTING row is a short-decay kind — never a Phase 11 row.
        if nearest_kind in config.MEMORY_DECAY_DAYS_BY_KIND:
            new_expires = datetime.now(timezone.utc) + timedelta(
                days=config.MEMORY_DECAY_DAYS_BY_KIND[nearest_kind]
            )
            await database.refresh_memory_expiry(self._pool, nearest_id, new_expires)
        return
```

Alternatively, scope the dedup `search_memories` call by `kind` so a `taste_episode` can only ever
dedup against another `taste_episode`. Add a regression test that writes a `taste_episode` whose nearest
neighbor is a `daily_batch` row and asserts `refresh_memory_expiry` is **not** called.

## Warnings

### WR-01: Per-user isolation gap in `taste_distill_batch` — the raise-prone DB fetch is *outside* the try, and the try wraps a call that never raises

**File:** `bot.py:998-1025`

**Issue:**
The loop's docstring promises "A single user's distill failure is swallowed (log.debug) and never
aborts the rest of the batch (T-13-08 / restore_queues per-guild continue discipline)." The actual
structure defeats this:

```python
for row in candidates:
    ...
    artist_rows = await database.get_user_artist_activity(...)   # NOT guarded — can raise
    phrases = logic_taste.summarize_taste(...)                   # NOT guarded
    if not phrases:
        continue
    raw_text = ...
    try:
        await memory_service.distill_and_remember(...)           # guarded, but see below
    except Exception as exc:
        log.debug(...)
```

`distill_and_remember` already catches *all* of its own exceptions internally
(`services/memory.py:482-486`), so it never raises — the `try/except` around it is effectively dead.
Meanwhile the genuinely raise-prone call, `database.get_user_artist_activity` (a live asyncpg round-trip
to Neon, subject to scale-to-zero / pool-exhaustion / transient drops on the residential-PC host), is
*unguarded*. If it raises for one user mid-loop, the whole batch aborts, every remaining candidate is
skipped, and the task errors out via `on_taste_distill_batch_error` — the opposite of the documented
per-user `continue` discipline.

**Fix:** Move the per-user body (the `get_user_artist_activity` fetch through `distill_and_remember`)
inside a single `try/except Exception` with a `continue`/log, so one user's DB hiccup cannot abort the
batch:

```python
for row in candidates:
    guild_id, user_id, tracks_in_window = row["guild_id"], row["user_id"], row["tracks_in_window"]
    if not logic_taste.has_min_activity(tracks_in_window, min_tracks=config.TASTE_MIN_ACTIVITY_TRACKS):
        continue
    try:
        artist_rows = await database.get_user_artist_activity(...)
        phrases = logic_taste.summarize_taste(...)
        if not phrases:
            continue
        raw_text = "Listening activity this week: " + "; ".join(phrases)
        await memory_service.distill_and_remember(...)
    except Exception as exc:
        log.debug("taste_distill_batch: error for guild=%s user=%s: %s", guild_id, user_id, exc)
        continue
```

### WR-02: `contains_number` backstop silently discards taste episodes for popular numbered/number-word artists

**File:** `services/memory.py:428-430` (backstop) via `bot.py:1018` (taste raw_text) and `models/memory.py:406-429`

**Issue:**
Phase 13 makes artist-name facts first-class: `summarize_taste` interpolates the raw `artist` string
into phrases (e.g. `"played {artist} heavily this week"`), which become the `raw_text` fed to
`distill()`. The distiller's deterministic `contains_number()` backstop then drops *any* produced fact
containing a digit **or a written count word**. For a large class of real artists this silently discards
the taste episode entirely:

- Digits: `Blink-182`, `Sum 41`, `Maroon 5`, `Matchbox Twenty` (as "20").
- Count words (`_NUMBER_WORDS_RE`): **`Twenty One Pilots`** matches both `twenty` and `one`;
  `Three Days Grace`, `Maroon` → not, but `The 1975`, `blink-one-eighty-two` etc.

`Twenty One Pilots` is a mainstream artist, so its taste episodes will *never* survive the firewall.
The test suite even acknowledges the gap (`test_taste_logic.py:144-149`) but scopes it out. The result
is invisible, systematic data loss of legitimate taste facts with no logging distinguishing "artist
name tripped the number filter" from "genuine count leak."

This is a correctness/quality tension inherent to reusing the Phase 11 count firewall on artist names;
it is not a security issue, but it degrades the feature for common inputs.

**Fix (pick one):**
- Preserve the artist token when applying the firewall — e.g. mask the known `artist` substring before
  running `contains_number` on the distilled fact, so only counts *outside* the artist name trigger a drop.
- Or skip the `contains_number` backstop for the `taste_episode` kind, since its `raw_text` provenance is
  already number-free by construction (`summarize_taste` never interpolates a count) — the only digits
  that can appear come from the artist name itself.
- At minimum, log at a distinguishable level when a `taste_episode` fact is dropped by `contains_number`
  so the silent loss is observable.

## Info

### IN-01: Unused taste-band config knobs (dead configuration)

**File:** `config.py:201-202`

**Issue:** `TASTE_BAND_HEAVY_PLAYS = 5` and `TASTE_BAND_FEW_PLAYS = 2` are defined with descriptive
comments ("qualitative band threshold: 'played heavily' vs 'a few times'") but are not referenced
anywhere in the codebase — `logic/taste.py::summarize_taste` uses fixed template phrases and never
consults a play-band threshold. Grep across the tree confirms zero non-config usages.

**Fix:** Either wire them into `summarize_taste` (if graded "heavily / a few times" phrasing was the
intent) or remove them to avoid implying behavior that does not exist.

---

_Reviewed: 2026-07-02T14:08:57Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
