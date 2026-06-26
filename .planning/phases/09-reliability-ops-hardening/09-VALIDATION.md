---
phase: 9
slug: reliability-ops-hardening
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-26
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
>
> **Scope note:** Phase 9 hardens Discord/process/network glue (health server, `on_ready`
> lifecycle, asyncio background tasks, asyncpg pool, yt-dlp). CONTEXT.md explicitly defers
> *test extraction* of this hardening logic to **Phase 10** — "Discord/process glue stays
> untested-by-design here." Consequently most Phase 9 behaviors are **manual-only** verification
> at the live-bot level. Pure, side-effect-free helpers introduced this phase (e.g. a throttle
> window, a transient-vs-permanent error classifier, a done-callback helper) ARE unit-testable
> and should get lightweight tests where cheap.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing `tests/` suite — pure unit + live-DB integration) |
| **Config file** | none dedicated — pytest discovery over `tests/` |
| **Quick run command** | `python -m pytest tests/ -q -k "not integration"` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | ~10–30 seconds (unit subset) |

---

## Sampling Rate

- **After every task commit:** Run the quick command (unit subset stays green)
- **After every plan wave:** Run the full suite
- **Before `/gsd-verify-work`:** Full suite green + manual live-bot checks below performed
- **Max feedback latency:** ~30 seconds (unit subset)

---

## Per-Task Verification Map

> Filled by the planner per task. Most Phase 9 tasks are process/Discord glue → **manual**
> (see Manual-Only table). Pure helpers → **unit**. No 3 consecutive pure-logic tasks should
> ship without an automated verify; glue tasks are exempt by the test-deferred scope above.

| Task ID | Plan | Wave | Requirement | Secure Behavior | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------------|-----------|-------------------|--------|
| (planner-filled) | — | — | REL-0X | N/A | unit / manual | `python -m pytest …` or manual | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] No new framework install required — `pytest` + `tests/` already present.

*Existing infrastructure covers all automatable phase logic. Glue behaviors are validated live.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `/health` returns 503 when MusicCog fails to load (strict mode) | REL-01 | HTTP server + cog-load state = live process glue | Boot bot with MusicCog forced to fail (or DB unreachable); `curl -s -o /dev/null -w "%{http_code}" localhost:<port>/health` → expect 503 + degraded body. Set `HEALTH_STRICT_STATUS=false` → expect 200. |
| Crashing background task surfaces in logs + error channel (throttled) | REL-02 | Requires a live failing `create_task` + Discord channel | Force `_prefetch_next_track` / `_post_auto_lyrics` to raise; confirm one log line per occurrence in `dexter.log` AND a throttled/deduped post in `ERROR_LOG_CHANNEL_ID` (repeat failures do not flood). |
| Slow/failed `tree.sync` recovers; bot still comes online | REL-03 | Requires Discord gateway + injected delay | Simulate a hanging/failing `bot.tree.sync`; confirm bot reaches ready, logs the failure, already-registered slash commands work, background sync retry fires. |
| `on_ready` re-entry guard never permanently wedges on a true hang | REL-04 | Requires a hang (no exception) inside `_initialize_once` | Inject a hang into `_initialize_once`; confirm `asyncio.wait_for` watchdog raises TimeoutError, pool is cleaned up, `_ready_initializing` resets, and the next ready event retries. |
| Slow DB query hits timeout + personality error, bot not blocked | REL-05 | Requires live query exceeding `command_timeout` | Run a query past `DB_COMMAND_TIMEOUT_SECONDS` (e.g. `pg_sleep`); confirm `asyncio.TimeoutError` is caught, user sees personality "took too long" message, bot stays responsive. |
| Transient youtube search/extract self-heals within bounded retry | REL-06 | Requires real/simulated transient yt-dlp failure | Force a transient `search()`/`extract()` failure; confirm bounded quick retry recovers; force a persistent failure and confirm fallback to throttled `update_ytdlp()` + retry, then a clean user-facing error. Confirm `ExtractorError.expected=True` (video unavailable) does NOT trigger retry/update. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify OR are listed as manual-only above with reason
- [ ] Sampling continuity: no 3 consecutive *pure-logic* tasks without automated verify
- [ ] Wave 0 covers all MISSING references (none required)
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s (unit subset)
- [ ] `nyquist_compliant: true` set in frontmatter once planner fills the verification map

**Approval:** pending
