---
phase: 12
slug: richer-music-ux
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-30
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `12-RESEARCH.md` §Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (in requirements.txt) + pytest-asyncio |
| **Config file** | none — run via `python -m pytest` from project root |
| **Quick run command** | `python -m pytest tests/test_skip_stats.py tests/test_autoqueue_validate.py tests/test_lyrics_lrclib.py -x` |
| **Full suite command** | `python -m pytest tests/ -x` |
| **Estimated runtime** | ~15–30 seconds (pure-unit subset is sub-second; full suite includes live-DB integration) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_skip_stats.py tests/test_autoqueue_validate.py tests/test_lyrics_lrclib.py -x`
- **After every plan wave:** Run `python -m pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 12-01 | 01 | 1 | UX-01 | — | guild_jams keyed by guild_id only; no cross-guild leakage | integration (asyncpg) | `python -m pytest tests/test_database_phase12.py -x` | ❌ W0 | ⬜ pending |
| 12-01 | 01 | 1 | UX-01 | — | `/jam load` truncates at queue cap | unit | `python -m pytest tests/test_jam_load.py -x` | ❌ W0 | ⬜ pending |
| 12-02 | 02 | 1 | UX-02 | — | min-plays floor suppresses noisy 1/1 rates | unit (pure) | `python -m pytest tests/test_skip_stats.py -x` | ❌ W0 | ⬜ pending |
| 12-02 | 02 | 1 | UX-02 | — | division/edge (0/0, 0/5, 5/5) handled | unit (pure) | `python -m pytest tests/test_skip_stats.py -x` | ❌ W0 | ⬜ pending |
| 12-03 | 03 | 1 | UX-03 | — | `strip_lrc_headers()` removes `[ti:]/[ar:]` lines | unit (pure) | `python -m pytest tests/test_lyrics_lrclib.py -x` | ❌ W0 | ⬜ pending |
| 12-03 | 03 | 1 | UX-03 | — | `_get_lrclib()` picks first non-instrumental; None when all instrumental/empty/HTTP-500 | unit (mocked aiohttp) | `python -m pytest tests/test_lyrics_lrclib.py -x` | ❌ W0 | ⬜ pending |
| 12-04 | 04 | 1 | UX-04 | — | `validate_youtube_match()` accepts valid, rejects mismatch, tolerates noise tokens | unit (pure) | `python -m pytest tests/test_autoqueue_validate.py -x` | ❌ W0 | ⬜ pending |
| 12-04 | 04 | 1 | UX-04 | — | loop falls through to next suggestion on full rejection | unit (mocked services) | `python -m pytest tests/test_autoqueue_validate.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_skip_stats.py` — UX-02 `compute_skip_rate` pure logic (min-plays floor, division edges)
- [ ] `tests/test_autoqueue_validate.py` — UX-04 `validate_youtube_match` + fall-through loop
- [ ] `tests/test_lyrics_lrclib.py` — UX-03 `strip_lrc_headers` + mocked `_get_lrclib` fetch
- [ ] `tests/test_jam_load.py` — UX-01 `/jam load` queue-cap truncation (pure/mock)
- [ ] `tests/test_database_phase12.py` — UX-01 `guild_jams` DB helpers (integration, requires live test DB)

*Pure-logic helpers (`logic/skip_stats.py`, `logic/autoqueue.py`, LRCLIB header stripper) follow the Phase 10 pure-helper convention and are unit-tested without Discord/DB.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `/jam` group round-trip in a live guild (save → add → load → list → delete) | UX-01 | Discord slash-command UX + voice enqueue path not unit-coverable | In a test guild: `/jam save mix`, `/jam add mix`, `/jam load mix`, `/jam list`, `/jam delete mix`; confirm ephemeral responses and queue enqueue |
| `/skips` embed renders server most-skipped + personal roast footer | UX-02 | Embed rendering + roast voice is presentation | Run `/skips` in a guild with skip history; confirm footer and min-plays "not enough data" path |
| `/lyrics` falls through to LRCLIB when Genius + AZLyrics miss | UX-03 | Depends on live third-party miss conditions | Trigger `/lyrics` on a track Genius/AZLyrics lack but LRCLIB has |
| Auto-queue rejects a hallucinated Gemini suggestion live | UX-04 | Depends on live Gemini + YouTube responses | Observe auto-queue round; confirm a non-matching suggestion is skipped, round still fills from valid ones |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
