# Phase 20: Owner Control Plane & Rate Observability - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-11
**Phase:** 20-owner-control-plane-rate-observability
**Areas discussed:** Blacklist storage, Owner control surface, RATE-01 usage counter, Silence & block UX

---

## Blacklist storage (the D-12 landmine)

### Where the blacklist lives

| Option | Description | Selected |
|--------|-------------|----------|
| Own `guild_blocklist` table | Dedicated table (guild_id PK, reason, blocked_at); MEM-04 purge never touches it — block survives removal by construction | ✓ |
| Keep `is_blocked` column | Reuse Phase 18's column; Phase 21 MEM-04 must special-case "purge except blocked row" | |

**User's choice:** Own `guild_blocklist` table (D-01).
**Notes:** Resolves the Phase 19 D-12 collision by construction — Phase 21 purges guild_config freely, zero carve-out logic in the scarred memory path.

### How the block is read at enforcement time

| Option | Description | Selected |
|--------|-------------|----------|
| In-memory blocked-set cache | Load-all at boot + push-invalidate; O(1) membership on interaction_check + join hot paths, no Neon round-trip (CONFIG-03) | ✓ |
| Live DB SELECT per check | Always fresh, no cache to invalidate — but a Neon round-trip on the command hot path | |

**User's choice:** In-memory blocked-set cache (D-02).

### Service ownership + the dead is_blocked column

| Option | Description | Selected |
|--------|-------------|----------|
| GuildConfigService owns it; leave is_blocked unused | Extend existing service (already load-all + push-invalidate); dead column documented, no destructive DDL | ✓ |
| New GuildBlocklistService; DROP is_blocked | Separate service + destructive migration | |
| Silenced too | Fold silenced read into same mechanism | |

**User's choice:** GuildConfigService owns it; is_blocked left dead/documented (D-03).

---

## Owner control surface

### Command shape

| Option | Description | Selected |
|--------|-------------|----------|
| `/guilds` group | list/silence/unsilence/leave/block/unblock; mirrors /memory,/playlist,/jam idiom | ✓ |
| Separate top-level commands | Flatter, but six commands clutter global command space | |
| Fold into /stats | Conflates read-only analytics with destructive actions | |

**User's choice:** `/guilds` app_commands.Group (D-04); lands in cogs/ops.py (D-05).

### Visibility / sync scope

| Option | Description | Selected |
|--------|-------------|----------|
| Global sync + inline is_owner, accept visibility | default_permissions is a UI hint; real gate is inline is_owner() | ✓ |
| Owner-guild-only sync | Truly hidden, but a second sync path, breaks if owner operates elsewhere | |

**User's choice:** Global sync + inline is_owner (D-06).

### Confirmation on destructive actions

| Option | Description | Selected |
|--------|-------------|----------|
| Execute immediately, ephemeral echo | Kill-switch speed; both ops reversible | ✓ |
| Danger-confirm button | Guards fat-finger, but treats reversible op as unrecoverable | |
| Confirm on leave only | Splits the difference; still unwarranted | |

**User's choice:** Execute immediately with in-persona ephemeral echo (D-07). Echo preview implied block also force-leaves — confirmed later as D-11.

---

## RATE-01 usage counter

### Counting & storage

| Option | Description | Selected |
|--------|-------------|----------|
| In-memory per-guild counter, since-boot | dict[guild_id->int]; zero schema, zero DB writes on hot path; "this session" is the actionable window | ✓ |
| DB-persisted per-guild daily counter | Durable history; DB write per call + new schema | |
| Rolling-window RPM per guild | Live pressure, but worse abuse signal than cumulative total | |

**User's choice:** In-memory since-boot counter (D-08).

### Tagging mechanics + guild-less/embed handling

| Option | Description | Selected |
|--------|-------------|----------|
| Optional guild_id kwarg; count guild-attributable chat/image only | None = not counted; embed() untagged (separate limiter) | ✓ |
| Tag everything incl. embeds, bucket None as 'system' | More complete; embeds on a limiter /guilds can't act on, 'system' row adds noise | |

**User's choice:** Optional guild_id kwarg on chat()/generate_image(); None uncounted; embed() untagged (D-09).

### /guilds list rendering

| Option | Description | Selected |
|--------|-------------|----------|
| Sorted by AI calls desc, paginated embed | Budget hog line one; LyricsPageView pagination; ephemeral | ✓ |
| Sorted by name/join date | Stable but buries the high-usage guild | |
| Single embed, top-N + summary | Silent truncation, violates no-silent-caps discipline | |

**User's choice:** Sorted by AI calls desc, paginated, ephemeral, no truncation (D-10).

---

## Silence & block UX

### block ↔ leave relationship

| Option | Description | Selected |
|--------|-------------|----------|
| block = leave + blacklist; leave standalone | Never blacklist a guild you're in; bare leave allows re-invite | ✓ |
| Fully independent flags | Footgun of blocked-but-present guild | |
| block implies leave; no standalone leave | OWNER-03 requires a force-leave capability | |

**User's choice:** block = teardown + blacklist; leave = teardown only; unblock does not re-join (D-11).

### Silenced-guild command UX

| Option | Description | Selected |
|--------|-------------|----------|
| Ephemeral in-persona notice | "i've been muted..."; avoids Discord's "did not respond" timeout | ✓ |
| Truly silent, no response | Looks like a crashed bot | |
| Ephemeral neutral notice | Forfeits persona for no gain | |

**User's choice:** Ephemeral in-persona notice for slash; ambient stays fully silent (D-12).

### interaction_check exemptions

| Option | Description | Selected |
|--------|-------------|----------|
| Exempt owner + DMs; check silenced AND blocked | Owner never locked out; DMs allowed; defense-in-depth on block | ✓ |
| No owner exemption | Owner could self-lock-out of /guilds unsilence | |
| Silenced only | Drops the defense-in-depth OWNER-05 names | |

**User's choice:** Exempt owner + DMs; refuse on silenced OR blocked (D-13). Silenced check also added to decide_ambient_channel + TOCTOU pre-send re-check (D-14).

---

## Claude's Discretion

Deferred to planner (do not re-ask): exact `guild_blocklist` DDL; DB helper shapes (load/insert/delete blocklist, silenced get/set); whether the silenced check is a new pure helper vs a branch in decide_ambient_channel; guild_id argument type on subcommands; the interaction_check wiring (CommandTree subclass vs bot.tree); all user-facing copy; exact Gemini call sites passing guild_id; pagination threshold; the mock-free-TDD vs live-DB vs untested-by-design test split.

## Deferred Ideas

- MEM-04 guild-data purge → Phase 21 (guild_blocklist deliberately out of its scope).
- Memory guild-scoping (MEM-01/02/03/05) → Phase 21.
- SCALE-F1 soft per-guild rate ceiling → conditional/future (RATE-01 is its prerequisite).
- DB-persisted / historical usage analytics → future (rejected D-08).
- Confirm/undo ceremony on leave/block → future (rejected D-07).
- /invite + OAuth2 URL → Phase 22. Landing page / README / badge / Pages CD / GHCR → Phase 23.
- Ripping out the dead is_blocked column → later cleanup at most.
