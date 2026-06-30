# Phase 12: Richer Music/UX - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-30
**Phase:** 12-richer-music-ux
**Areas discussed:** Server playlists (UX-01), Skip analytics (UX-02), Lyrics fallback (UX-03), Auto-queue validation (UX-04)

---

## Server playlists (UX-01) — edit permissions

| Option | Description | Selected |
|--------|-------------|----------|
| Anyone in the server | Any member can save/overwrite/delete jams; most collaborative, no role checks | ✓ |
| Creator or admins only | Only creator / Manage-Server can overwrite/delete; needs created_by + checks | |
| Anyone adds, admins delete | Anyone creates/appends; only admins delete | |

**User's choice:** Anyone in the server
**Notes:** Collaborative "shared community mixtape" model, no ownership friction.

---

## Server playlists (UX-01) — command surface

| Option | Description | Selected |
|--------|-------------|----------|
| New /jam group | Separate /jam save\|load\|list\|delete, distinct from user-global /playlist | ✓ |
| Add scope to /playlist | Extend /playlist with me\|server scope arg | |

**User's choice:** New /jam group
**Notes:** Clean mental model — /playlist = yours, /jam = the server's.

---

## Server playlists (UX-01) — jam data model

| Option | Description | Selected |
|--------|-------------|----------|
| Snapshot of current queue | /jam save snapshots the queue, like /playlist save | |
| Incremental song list | Living list you add now-playing to over time | ✓ |

**User's choice:** Incremental song list — but asked "how do we get out of a jam tho?", prompting a model-clarification follow-up.

### Follow-up — jam interaction model

| Option | Description | Selected |
|--------|-------------|----------|
| A — stored named list | /jam add appends now-playing; /jam load queues it; no session, nothing to exit | ✓ |
| B — active jam session | /jam start → jam mode → /jam stop; stateful, more edge cases | |

**User's choice:** A — stored named list
**Notes:** Resolved the "getting out" question — a jam is just a named server collection that accumulates songs; there's no session to escape. Session-mode (B) deferred.

---

## Skip analytics (UX-02) — what it shows

| Option | Description | Selected |
|--------|-------------|----------|
| Most-skipped songs (server) | Hall of shame; reuse most_skipped query | |
| Per-user skip habits | Each user's skip rate | |
| Both — songs + a personal line | Server most-skipped + caller's own skip rate footer | ✓ |

**User's choice:** Both — songs + a personal line

---

## Skip analytics (UX-02) — surface

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated /skips command | Own embed, keeps /stats clean, room for leaderboard + roast | ✓ |
| Fold into /stats | Add skip section to existing /stats embed | |

**User's choice:** Dedicated /skips command

---

## Skip analytics (UX-02) — noise guardrail

| Option | Description | Selected |
|--------|-------------|----------|
| Min-plays floor | Only show rate once ≥ N data points | |
| Raw counts, no floor | Show regardless of sample size | |
| You decide | Claude picks a sensible floor | ✓ |

**User's choice:** You decide → Claude: min-plays floor via `SKIP_STATS_MIN_PLAYS` (default 5).

---

## Skip analytics (UX-02) — time window

| Option | Description | Selected |
|--------|-------------|----------|
| All-time | Aggregate over all song_history | |
| Rolling window | Last N days | |
| You decide | Claude picks simpler option | ✓ |

**User's choice:** You decide → Claude: all-time (simplest, fits existing queries).

---

## Lyrics fallback (UX-03) — third source

| Option | Description | Selected |
|--------|-------------|----------|
| LRCLIB | Free, no key, clean JSON API, built for players | ✓ |
| lyrics.ovh | Free, no key, simple but flakier/thinner catalog | |
| Another scrape source | Best coverage but brittle like AZLyrics | |

**User's choice:** LRCLIB
**Notes:** (Question re-asked once at user's request before answering.)

---

## Auto-queue validation (UX-04) — match rule

| Option | Description | Selected |
|--------|-------------|----------|
| Fuzzy title+artist | Result must fuzzily contain both title AND artist (normalized) | ✓ |
| Title-only fuzzy | Only title matched; looser | |
| Strict token overlap | ≥80% token overlap; tightest, may over-reject | |

**User's choice:** Fuzzy title+artist

---

## Auto-queue validation (UX-04) — search breadth + on-reject

| Option | Description | Selected |
|--------|-------------|----------|
| Widen search, pick best match | count 1→~3, pick first that passes fuzzy check | ✓ |
| Validate top result only | Keep count=1, accept/reject single hit | |

**User's choice:** Widen search, pick best match
**On reject:** Try next suggestion to keep the round full (capped at AUTO_QUEUE_SONGS_PER_ROUND).

---

## Claude's Discretion

- Skip-rate noise floor (`SKIP_STATS_MIN_PLAYS`, default ~5).
- Skip-rate time window → all-time.
- Per-guild jam cap value + `AUTO_QUEUE_SEARCH_CANDIDATES` default (~3).
- Fuzzy-matching implementation (substring vs token-set / difflib) as a pure unit-tested helper.
- LRCLIB request shape (/api/get vs /api/search).

## Deferred Ideas

- Active "jam session" mode (/jam start…/jam stop) — its own phase.
- Rolling time-window / re-rollable skip leaderboards.
- Per-jam edit permissions / ownership (creator-or-admin-only).
