---
phase: 16
slug: proactive-memory-callbacks
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-03
---

# Phase 16 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `16-RESEARCH.md` §Validation Architecture (HIGH confidence, all
> line anchors confirmed byte-exact against the live repo).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (already in `requirements.txt`; strict mode — explicit `@pytest.mark.asyncio`, not `asyncio_mode=auto`) |
| **Config file** | none — no `pytest.ini`/`pyproject.toml`; tests self-mark |
| **Quick run command** | `pytest tests/test_proactive_logic.py tests/test_database_phase16.py -x` |
| **Full suite command** | `pytest -x` |
| **Estimated runtime** | ~15–30 seconds (pure/static tiers); live-DB tier skips without `TEST_DATABASE_URL` |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_proactive_logic.py tests/test_database_phase16.py -x` (fast, pure + static-inspection, no live DB)
- **After every plan wave:** Run `pytest -x` (full suite — mirrors Phase 13–15 gate discipline)
- **Before `/gsd-verify-work`:** Full suite must be green; live-DB opt-out round-trip runs when `TEST_DATABASE_URL` is configured
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

| Req ID | Behavior | Test Type | Automated Command | File Exists |
|--------|----------|-----------|-------------------|-------------|
| PROACT-01 | `should_fire_proactive_callback` gate math: opt-out short-circuit, chance-roll boundary (`<` not `<=`), daily-cap boundary (`>=` fails, ceiling) | unit (pure, mock-free) | `pytest tests/test_proactive_logic.py -x` | ❌ W0 |
| PROACT-01 | New chance strictly below `MEMORY_CALLBACK_CHANCE` (0.35) and `UNPROMPTED_ROAST_CHANCE` (0.30) — config-level invariant | unit (value inspection) | `pytest tests/test_proactive_logic.py -k rarer_than_ambient -x` | ❌ W0 |
| PROACT-01 | Ambient 0.35 `MEMORY_CALLBACK_CHANCE` gate inside `_generate_ambient_roast` stays intact for the two existing voice-event call sites (regression lock) | unit (source, existing test extended) | `pytest tests/test_ambient_recall_cadence.py -x` | ✅ extend |
| PROACT-01 | Recall-floor silent-skip: `recall()` → `[]` produces zero Discord send, no exception | unit (behavioral, mocked recall) | `pytest tests/test_proactive_events.py -k recall_floor -x` | ❌ W0 |
| PROACT-01 | Reply anchored (`message.reply`, not `channel.send`) with `AllowedMentions.none()` | unit (behavioral, mocked Message) | `pytest tests/test_proactive_events.py -k reply_anchor -x` | ❌ W0 |
| PROACT-01 | Accuracy firewall: proactive glue never pipes a live-SQL numeric-stat helper into reply text outside the firewalled `_generate_ambient_roast` path | unit (source inspection) | `pytest tests/test_proactive_events.py -k accuracy_firewall -x` | ❌ W0 |
| PROACT-01 | `pre_recalled_memories` param, when provided, bypasses the internal chance roll (Pitfall-1 fix is real, not cosmetic) | unit (behavioral) | `pytest tests/test_ambient_recall_cadence.py -k pre_recalled -x` | ✅ extend |
| PROACT-02 | Opt-out getter/setter touch ONLY `user_profiles`, never `user_memories` (structural independence from `/memory forget`) | unit (source inspection) | `pytest tests/test_database_phase16.py -k opt_out_scope -x` | ❌ W0 |
| PROACT-02 | `callbacks off` → `on` round-trips the flag; default (no prior row) reads opted-in (`False`) | live-DB integration (skips w/o `TEST_DATABASE_URL`) | `pytest tests/test_database_phase16.py -k opt_out_roundtrip -x` | ❌ W0 |
| PROACT-02 | `/memory callbacks` subcommand self-scoped (no `target` param), ephemeral, in-character | unit (behavioral, mocked interaction) | `pytest tests/test_memory_command.py -k callbacks -x` | ✅ extend |
| PROACT-02 | Opting out does NOT delete/alter any `user_memories` row (zero-row-touched, distinct from forget) | live-DB integration (optional) | `pytest tests/test_database_phase16.py -k zero_memories_touched -x` | ❌ W0 |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_proactive_logic.py` — NEW; mirrors `tests/test_roast_logic.py`. Full branch/boundary coverage for `should_fire_proactive_callback` (opt-out, chance boundary, daily-cap boundary, threshold overrides) + config-value assertion `PROACTIVE_CALLBACK_CHANCE < UNPROMPTED_ROAST_CHANCE` and `< MEMORY_CALLBACK_CHANCE`.
- [ ] `tests/test_database_phase16.py` — NEW; mirrors `tests/test_database_phase15.py` two-tier shape. Static signature guard on `set_proactive_opt_out`/`get_proactive_opt_out` (scoped to `user_profiles`, single-identity + one boolean, never touches `user_memories`) + live-DB round-trip + cross-independence with `delete_all_user_memories`.
- [ ] `tests/test_proactive_events.py` — NEW; mirrors `tests/test_ambient_recall_cadence.py` mock style. Behavioral proof of `on_message` glue: designated-channel gate, empty-recall silent no-op, `message.reply` + `AllowedMentions.none()` on fire, daily-counter increments only on actual fire.
- [ ] `tests/test_ambient_recall_cadence.py` — MODIFIED; verify `test_ambient_surfaces_retain_gate` still green after the `pre_recalled_memories` signature change + new assertion that the param bypasses the internal chance roll.
- [ ] `tests/test_memory_command.py` — MODIFIED; add `test_memory_callbacks_off_then_on`, `test_memory_callbacks_is_self_scoped`, `test_memory_callbacks_response_ephemeral`.
- Framework install: none — pytest/pytest-asyncio already present.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| A live proactive callback actually fires at a real active moment and reads as a dry bit, not surveillance | PROACT-01 | Requires a running bot on a residential IP + real Gemini + real Discord channel activity; the "feel" target is subjective | Parked behind the always-on host (per Phase 11/13/14/15 UAT precedent) — post in the designated channel repeatedly, confirm a rare reply-anchored callback with no ping |
| `/memory callbacks off` visibly silences the surface in-Discord while `/memory view` still shows intact memories | PROACT-02 | Discord slash-command + ephemeral UX check on a live client | Parked behind host — run `/memory callbacks off`, confirm ephemeral in-character reply, confirm `/memory view` unchanged |

*Live-DB `opt_out_roundtrip` / `zero_memories_touched` are automated but skip without `TEST_DATABASE_URL` — they run at the phase gate when a live DB is configured.*

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
