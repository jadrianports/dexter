# Phase 21: Memory Scoping & Guild Data Lifecycle - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-14
**Phase:** 21-memory-scoping-guild-data-lifecycle
**Areas discussed:** Legacy NULL corpus (MEM-03), Scoping blast radius (MEM-05 scar), Purge scope & hook (MEM-04), Descope go/no-go framing

**Pre-decided (carried forward, not re-asked):** hybrid memory scoping + purge-on-removal
(REQUIREMENTS.md Key Decisions); `guild_blocklist` is its own table and is out of purge scope
(Phase 20 D-01); the documented fallback is "keep memory global + disclose"; the Descope Rule is a
standing user directive.

**Scouting finding that framed every question:** all unprompted write surfaces already stamp a real
`guild_id`; only `daily_batch` writes `NULL`.

---

## Legacy NULL corpus (MEM-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Grandfather NULL as global | Recall filter `WHERE guild_id = $1 OR guild_id IS NULL`. New memories guild-scoped; pre-existing NULL corpus stays recallable everywhere. Satisfies MEM-03's "not silently made unrecallable". | ✓ |
| Strict guild-only | `WHERE guild_id = $1`. Cleanest scoping but silently blinds the pre-existing NULL corpus. Tension with MEM-03. | |
| Backfill NULL rows | One-time migration stamping NULL rows with a guild_id. `daily_batch` has no attributable single guild — can't be done correctly. | |

**User's choice:** Grandfather NULL as global (recommended option)
**Notes:** Low-risk because the NULL corpus is bounded and known — only `daily_batch` writes it. → CONTEXT D-01.

---

## Scoping blast radius (MEM-05 scar)

| Option | Description | Selected |
|--------|-------------|----------|
| Read-path only | Guild filter on `recall()`/`search_memories` reads ONLY. `remember`/dedup/eviction/`expires_at` self-refresh stay `user_id`-scoped and byte-identical — the CR-13-01 scar path untouched. | ✓ |
| Also guild-scope dedup + eviction | Per-guild dedup/eviction too. Reopens the `expires_at`/cross-kind corruption scar and enlarges the regression surface for negligible gain. | |

**User's choice:** Read-path only (recommended option)
**Notes:** Read/write asymmetry is deliberate — a user's own facts deduping across guilds is harmless; cap-eviction is a per-user budget and correctly stays global. Flagged seam consequence: `guild_id` presence alone cannot distinguish `/roast` (scope) from `/ask` (global), since both run in a guild — `recall()` needs an **explicit opt-in**. → CONTEXT D-02.

---

## Purge scope & hook (MEM-04)

| Option | Description | Selected |
|--------|-------------|----------|
| `guild_id=$1`, single `on_guild_remove` hook | Delete `guild_config`/`guild_queues`/`guild_jams`/`user_memories WHERE guild_id=$1` (NOT NULL). One hook covers natural-leave AND force-leave/block (both call `guild.leave()`). Never touches `guild_blocklist`; wrapped so failure can't crash removal. | ✓ |
| Also purge the guild's NULL-row share | NULL rows can't be attributed to a guild — no correct "this guild's share". | |
| Hook each teardown site separately | Purge in `on_guild_remove` + `ops.py` leave + block. Redundant; risks double-delete or a missed path. | |

**User's choice:** `guild_id=$1`, single `on_guild_remove` hook (recommended option)
**Notes:** Phase 20 D-01 (blocklist in its own table) is what makes this a clean `DELETE` with no "except if blocked" carve-out. → CONTEXT D-03.

---

## Descope go/no-go framing

| Option | Description | Selected |
|--------|-------------|----------|
| Attempt hybrid; descope only on a real tripwire | Ship MEM-02 + MEM-04 unconditionally. Attempt MEM-01/03/05 — writes already carry `guild_id` and the read-path-only approach sidesteps the scar. Fall back to global+disclose per-requirement only if a named tripwire actually fires at plan time. | ✓ |
| Pre-authorize straight-to-fallback | Skip the scoping attempt; ship only MEM-02 + MEM-04, keep memory global, disclose in PORT-04. Lowest risk, but surrenders MEM-01 when the code path now looks safe. | |

**User's choice:** Attempt hybrid; descope only on a real tripwire (recommended option)
**Notes:** Per the standing user-directed Descope Rule, a genuine tripwire descope needs no further user permission — record it in PROJECT.md Key Decisions and continue. → CONTEXT D-04.

---

## Claude's Discretion

- Exact `recall()`/`search_memories()` signature for the guild-scoping opt-in (kwarg flag vs dedicated scope param); must keep non-opted-in callers byte-identical.
- Exact call-site inventory of which `recall()` sites opt in. MEM-01 names `/roast` + ambient + proactive. **Research items:** the music-command memory callback (`cogs/music.py`, currently passes `""`) and the auto-queue positive-taste-blend recall over voice members' `taste_episode`.
- Whether the guild clause is a conditional branch in `search_memories` SQL (Phase 14 `kind`-clause precedent) vs a new helper.
- Purge helper shape (one `purge_guild_data` vs per-table helpers; transaction vs sequential; DELETE ordering). New helpers required — no per-guild delete exists for `guild_queues`/`user_memories`.
- Exact MEM-05 regression-test shape (mock-free for pure logic; live-DB for search/dedup/`expires_at` interaction).
- Whether a pure `logic/` seam is warranted for the scope decision (likely overkill).

## Deferred Ideas

- Full guild-scoped `/ask`, or per-user opt-in cross-guild sharing → **MEM-F3** (Future Requirements).
- Vision → RAG memory persistence → **MEM-F2**.
- Salience reinforcement → **MEM-F1**.
- Guild-scoping dedup/eviction → deliberately rejected (D-02); revisit only if a real cross-guild dedup problem is ever observed.
- Ripping out the dead `guild_config.is_blocked` column → left in place since Phase 20 D-03.
- PORT-04 disclosure copy → **Phase 23** (this phase only records the decision in PROJECT.md).
