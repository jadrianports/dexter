# Phase 9: Reliability & Ops Hardening - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-26
**Phase:** 9-Reliability & Ops Hardening
**Areas discussed:** Health truthfulness, Failure visibility, Startup recovery, Degraded-path UX

---

## Health truthfulness (REL-01)

### Status code

| Option | Description | Selected |
|--------|-------------|----------|
| Configurable, default 503 | Env flag `HEALTH_STRICT_STATUS` (default true) → 503+degraded body on PC now; flip to false to restore always-200 for a kill-on-non-200 host. | ✓ |
| Always 503, no flag | Just 503 when degraded, 200 when healthy; fewer moving parts but reintroduces D-28 risk if returning to strict cloud. | |

**User's choice:** Configurable, default 503 (asked for a recommendation first; agreed with it).
**Notes:** Resolves the REL-01 ↔ D-28 (Koyeb kill-loop) tension. 24/7 cloud is parked, so strict
is safe today; flag is the escape hatch for a future strict host.

### Critical set

| Option | Description | Selected |
|--------|-------------|----------|
| MusicCog + DB + gateway | Add MusicCog-load to existing DB + gateway checks. | ✓ |
| All cogs + DB + gateway | Any cog failing marks degraded; risks false degraded on key-less runs. | |
| You decide | Claude picks during planning. | |

**User's choice:** "you decide, analyze the code make the right choice" → locked to MusicCog + DB
+ gateway.
**Notes:** AI/Imagine excluded — they load only when `GEMINI_API_KEY` is set, so including them
would emit false "degraded" on a key-less run.

---

## Failure visibility (REL-02)

### Surface destination

| Option | Description | Selected |
|--------|-------------|----------|
| Logs + Discord error channel | dexter.log AND `ERROR_LOG_CHANNEL_ID`. | ✓ |
| Logs only | dexter.log / error.log via done-callback only. | |
| You decide | Per-task choice during planning. | |

**User's choice:** Logs + Discord error channel.

### Noise control

| Option | Description | Selected |
|--------|-------------|----------|
| Rate-limited / deduped | Log every occurrence; throttle/collapse channel posts. | ✓ |
| Every crash, every time | Post each crash individually. | |

**User's choice:** Rate-limited / deduped.
**Notes:** Mirror the existing yt-dlp self-update throttle pattern.

---

## Startup recovery (REL-03/04)

### Sync failure behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Proceed online + retry in background | Timeout-wrap sync; on fail, come online anyway + background retry. | ✓ |
| Retry with backoff, then proceed | Block on bounded retries before coming online. | |
| Fail fast / log only | Log and continue, no retry. | |

**User's choice:** Proceed online + retry in background.

### Init guard watchdog

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — timeout-wrap init | `asyncio.wait_for` on `_initialize_once`; timeout treated as failure (log, clean pool, reset guard). | ✓ |
| Keep as-is (finally reset) | Accept that an infinite hang with no exception is rare. | |

**User's choice:** Yes — timeout-wrap init.
**Notes:** Closes REL-04: `finally` only resets the guard on a *raised* exception, not a true hang.

---

## Degraded-path UX (REL-05/06)

### DB query timeout

| Option | Description | Selected |
|--------|-------------|----------|
| Pool-wide default + clean error | Default `command_timeout` on the pool + personality "took too long" message. | ✓ |
| Per-query timeouts on heavy ones | Explicit timeouts only on leaderboard/history. | |
| You decide | Claude chooses mechanism. | |

**User's choice:** Pool-wide default + clean error.
**Notes:** Pool default is the required floor; per-query timeouts allowed on top at discretion.

### YouTube search/extract self-heal

| Option | Description | Selected |
|--------|-------------|----------|
| Quick retry, then yt-dlp-update fallback | Fast bounded retry first; only then throttled yt-dlp self-update + retry. | ✓ |
| Mirror download() exactly | Throttled yt-dlp self-update then retry once. | |
| Simple bounded retry only | Retry a couple times, no yt-dlp update. | |

**User's choice:** Quick retry, then yt-dlp-update fallback.
**Notes:** Reuse `update_ytdlp()` + `_UPDATE_THROTTLE_SECONDS` from `services/youtube.py` as the
fallback tier.

---

## Claude's Discretion

- Exact timeout values (sync, init watchdog, pool `command_timeout`, retry backoff).
- Dedup mechanism for throttled channel posts (window vs error-signature vs both).
- Whether REL-05 adds per-query timeouts on top of the pool default.
- Done-callback helper shape for REL-02 (shared utility vs inline).
- Critical-set composition (delegated: locked to MusicCog + DB + gateway).

## Deferred Ideas

None — discussion stayed within phase scope.
