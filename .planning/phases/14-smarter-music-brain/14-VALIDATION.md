---
phase: 14
slug: smarter-music-brain
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-02
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing; `tests/conftest.py` provides the live-DB `pool` fixture that skips cleanly when Postgres is unavailable) |
| **Config file** | none required (existing suite runs without pytest.ini) |
| **Quick run command** | `python -m pytest tests/test_config.py tests/test_database_phase14.py tests/test_memory.py tests/test_autoqueue_validate.py tests/test_taste_logic.py tests/test_prompts.py -q` |
| **Full suite command** | `python -m pytest tests/ -q` (650 pass / 0 fail baseline per Phase 13 close) |
| **Estimated runtime** | pure/source tests sub-second; live-DB cases skip when no Postgres |

---

## Sampling Rate

- **After every task commit:** Run the touched-module quick command for that plan (see per-task map).
- **After every plan wave:** Run `python -m pytest tests/ -q`.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** < 30s (pure/source tests); live-DB cases are opportunistic.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 14-01-T1 | 14-01 | 1 | BRAIN-01/02 | — | 6 tuning knobs importable, positive ints | unit | `pytest tests/test_config.py -q` | ✅ existing | ⬜ pending |
| 14-01-T2 | 14-01 | 1 | BRAIN-01/02 | T-14-01/T-14-02 | 3 aggregate helpers: bound `$N`, WHERE guild_id, no cross-user attribution | source + integration | `pytest tests/test_database_phase14.py -q` | ❌ W0 (new file) | ⬜ pending |
| 14-01-T3 | 14-01 | 1 | BRAIN-01 | T-14-03 | `search_memories`/`recall` kind=None byte-identical; taste_episode filter works (OQ1) | unit + integration | `pytest tests/test_memory.py -q` | ✅ existing | ⬜ pending |
| 14-02-T1 | 14-02 | 1 | BRAIN-01 | — | `is_recently_skipped_artist` subset-match, vacuous-empty, no difflib (D-02) | unit (tdd) | `pytest tests/test_autoqueue_validate.py -q` | ✅ existing | ⬜ pending |
| 14-02-T2 | 14-02 | 1 | BRAIN-01 | T-14-02 | `select_positive_taste_context` round-robin/dedup/cap, unattributed (D-03) | unit (tdd) | `pytest tests/test_taste_logic.py -q` | ✅ existing | ⬜ pending |
| 14-02-T3 | 14-02 | 1 | BRAIN-01/02/03 | T-14-03 | recommendation prompt byte-identical when empty; jam builder parse_suggestions-compatible; discover builder firewall-safe | unit (tdd) | `pytest tests/test_prompts.py tests/test_autoqueue_parse.py -q` | ✅ existing | ⬜ pending |
| 14-03-T1 | 14-03 | 2 | BRAIN-01 | T-14-02 | negative + positive hint wired; member-set reuse; scar #2 intact | source | `pytest tests/test_autoqueue_wiring.py -q` | ❌ W0 (new file) | ⬜ pending |
| 14-03-T2 | 14-03 | 2 | BRAIN-01 | T-14-03 | D-02 hard filter as independent 2nd gate; validate_youtube_match unchanged | source + unit | `pytest tests/test_autoqueue_wiring.py tests/test_autoqueue_validate.py -q` | ❌ W0 (new file) | ⬜ pending |
| 14-04-T1 | 14-04 | 2 | BRAIN-02 | T-14-02/T-14-03 | SQL-derived picks, Gemini voice-only (no parse_suggestions), cold-start message | source | `pytest tests/test_discover.py -q` | ❌ W0 (new file) | ⬜ pending |
| 14-04-T2 | 14-04 | 2 | BRAIN-02 | — | one-shot confirm-to-queue view (finite timeout), duration cap, scar #2 | source | `pytest tests/test_discover.py -q` | ❌ W0 (new file) | ⬜ pending |
| 14-05-T1 | 14-05 | 2 | BRAIN-03 | T-14-03/T-14-05 | seed from existing jam, validate every candidate, none-survive leaves snapshot untouched | source | `pytest tests/test_jam_suggest.py tests/test_autoqueue_validate.py -q` | ❌ W0 (new file) | ⬜ pending |
| 14-05-T2 | 14-05 | 2 | BRAIN-03 | T-14-03 | propose-and-confirm view (finite timeout); save_jam only on confirm | source | `pytest tests/test_jam_suggest.py -q` | ❌ W0 (new file) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

New test files created WITHIN their owning task (TDD-style — no separate Wave 0 plan needed; each
producing task creates its own scaffold before/with implementation):

- [ ] `tests/test_database_phase14.py` — static source-assertions (always run) + live-DB cross-user-safety cases for the 3 new aggregate helpers (created in 14-01-T2)
- [ ] `tests/test_autoqueue_wiring.py` — `inspect.getsource` assertions on `try_auto_queue` wiring + scar-#2 guard (created in 14-03-T1)
- [ ] `tests/test_discover.py` — `/discover` source-assertions (firewall, cold-start, confirm view) (created in 14-04-T1)
- [ ] `tests/test_jam_suggest.py` — `/jam suggest` source-assertions (validation gate, none-survive, confirm-only write) (created in 14-05-T1)

Existing files extended in place: `tests/test_config.py`, `tests/test_memory.py`,
`tests/test_autoqueue_validate.py`, `tests/test_taste_logic.py`, `tests/test_prompts.py`.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live auto-queue actually stops re-suggesting a repeatedly-skipped artist across rounds | BRAIN-01 | Requires running bot + Discord voice + Gemini API | Deferred to live-runtime UAT (parked behind residential host) |
| `/discover` surfaces a real adjacent artist and queues it on confirm; cold-start guild shows in-character message | BRAIN-02 | Requires running bot + seeded guild history + Gemini | Deferred to live-runtime UAT (parked) |
| `/jam suggest` offers validation-passing additions and writes only on confirm; all-hallucinated run shows "nothing landed" | BRAIN-03 | Requires running bot + Gemini + YouTube search | Deferred to live-runtime UAT (parked) |

Note: the SECURE behaviors behind BRAIN-01/02/03 (bound-param SQL, no cross-user attribution,
validation-gated suggestions, unattributed taste blend, scar-#2 guard) all have AUTOMATED source /
unit / live-DB coverage above — only the end-to-end live-Discord UX feel is manual-deferred.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (each producing task carries its own test creation)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (4 new test files created within their owning tasks)
- [x] No watch-mode flags
- [x] Feedback latency < 30s (pure/source tests)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planner — 2026-07-02
