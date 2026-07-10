---
phase: 20
slug: owner-control-plane-rate-observability
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-11
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml / pytest.ini (existing) |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~60 seconds |

Live-DB tests (blocklist CRUD, silenced round-trip) require `TEST_DATABASE_URL`. CI supplies a `pgvector/pgvector:pg16` service container (Phase 18 D-15) so they actually run; a local run without `TEST_DATABASE_URL` skips them cleanly (conftest.py skip-on-connection guard). The autonomous gate (`pytest --collect-only`) needs no DB.

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 20-01-T1 | 20-01 | 1 | OWNER-04, OWNER-02 | T-20-04, T-20-08 | guild_blocklist own table + param-only helpers | live-DB (helper) + static shape | `python -c "import database,inspect; s=inspect.getsource(database); assert 'CREATE TABLE IF NOT EXISTS guild_blocklist' in s"` | Missing — created in this task | ⬜ pending |
| 20-01-T2 | 20-01 | 1 | OWNER-04, OWNER-02 | T-20-04 | blocklist survives a guild_config purge (D-01 durability) | live-DB + static shape | `pytest tests/test_database_phase20.py -q --collect-only` (+ live when DB present) | Missing — created in this task | ⬜ pending |
| 20-02-T1 | 20-02 | 1 | OWNER-05, OWNER-06, OWNER-02 | T-20-02, T-20-06, T-20-03 | silenced structural silence + owner-exempt/both-flags predicate | mock-free TDD (pure) | `pytest tests/test_guild_config_logic.py -q -k "silenced or interaction_allowed"` | Exists (additive) | ⬜ pending |
| 20-02-T2 | 20-02 | 1 | OWNER-05, OWNER-06, OWNER-02 | T-20-02, T-20-06 | branch coverage of both pure additions | mock-free TDD (pure) | `pytest tests/test_guild_config_logic.py -q` | Exists (additive) | ⬜ pending |
| 20-03-T1 | 20-03 | 1 | RATE-01 | T-20-09, T-20-10 | counter is observability-only, never a gate; embed untagged | mock-free unit (fake client) | `pytest tests/test_gemini_service.py -q -k "guild_usage or embed"` | Missing — created in T3 | ⬜ pending |
| 20-03-T2 | 20-03 | 1 | RATE-01 | T-20-09 | guild_id threaded; daily_batch passes None | structural (ast.parse) + regression | `python -c "import ast;[ast.parse(open(f,encoding='utf-8').read()) for f in ['cogs/ai.py','cogs/imagine.py','cogs/library.py','cogs/music.py','services/memory.py']]"` | n/a (call-site edits) | ⬜ pending |
| 20-03-T3 | 20-03 | 1 | RATE-01 | T-20-09 | increment on guild-attributable, skip None, embed untagged | mock-free unit | `pytest tests/test_gemini_service.py -q` | Missing — created in this task | ⬜ pending |
| 20-04-T1 | 20-04 | 2 | OWNER-04, OWNER-02 | T-20-04, T-20-11, T-20-12 | O(1) cache reads; write-then-mutate; independent fail-open | service (fake-pool) | `pytest tests/test_guild_config_service.py -q -k "blocked or silence"` | Exists (additive) | ⬜ pending |
| 20-04-T2 | 20-04 | 2 | OWNER-04, OWNER-02 | T-20-11, T-20-12 | blocked-set load + push-invalidate + fail-open isolation | service (fake-pool) | `pytest tests/test_guild_config_service.py -q` | Exists (additive) | ⬜ pending |
| 20-05-T1 | 20-05 | 2 | RATE-01 | T-20-02 | ambient Gemini calls tag guild_id | structural (ast.parse) + regression | `pytest tests/test_proactive_events.py -q` | Exists (additive) | ⬜ pending |
| 20-05-T2 | 20-05 | 2 | OWNER-06, OWNER-02 | T-20-02, T-20-13 | pre-send re-check suppresses a mid-flight silence (SC-2) | glue + regression | `pytest tests/test_proactive_events.py -q` | Exists (additive) | ⬜ pending |
| 20-05-T3 | 20-05 | 2 | OWNER-06, OWNER-02 | T-20-02 | silenced-mid-flight locked; default-False keeps existing cadence | regression (mock) | `pytest tests/test_proactive_events.py -q` | Exists (additive) | ⬜ pending |
| 20-06-T1 | 20-06 | 3 | OWNER-05, OWNER-06, OWNER-02 | T-20-03, T-20-06, T-20-14, T-20-15 | one choke point; owner/DM exempt; refusal sent inline; boot-race fail-open | Discord/process glue — untested-by-design (structural review + clean boot) | `python -c "import ast;src=open('bot.py',encoding='utf-8').read();ast.parse(src);assert 'class DexterCommandTree' in src and 'tree_cls=DexterCommandTree' in src and 'decide_interaction_allowed' in src"` | n/a (glue) | ⬜ pending |
| 20-06-T2 | 20-06 | 3 | OWNER-04 | T-20-04 | block-check-first before onboarding; re-invite-proof | Discord/process glue — untested-by-design | `python -c "import ast;src=open('bot.py',encoding='utf-8').read();ast.parse(src);j=src.split('async def on_guild_join')[1].split('async def on_guild_remove')[0];assert 'is_blocked(str(guild.id))' in j and j.index('is_blocked')<j.index('insert_guild_config_if_absent')"` | n/a (glue) | ⬜ pending |
| 20-07-T1 | 20-07 | 3 | OWNER-01, RATE-01 | T-20-07 | sorted/paginated/ephemeral list; plain-text names, backtick ids | glue untested-by-design + structural test | `python -c "import ast;ast.parse(open('cogs/ops.py',encoding='utf-8').read());import config;assert hasattr(config,'GUILDS_LIST_PAGE_SIZE')"` | Missing — test created in T3 | ⬜ pending |
| 20-07-T2 | 20-07 | 3 | OWNER-02 | T-20-01, T-20-05 | inline is_owner; guild_id parse never raises; honest no-row report | glue + structural | `python -c "import ast;s=open('cogs/ops.py',encoding='utf-8').read();ast.parse(s);assert 'silence_guild' in s and 'unsilence_guild' in s"` | n/a (glue) | ⬜ pending |
| 20-07-T3 | 20-07 | 3 | OWNER-03, OWNER-04, OWNER-06 | T-20-01, T-20-05, T-20-16 | /stop teardown via get_guild; block=teardown+blacklist; six-subcommand is_owner gate | structural test (inspect.getsource) | `pytest tests/test_guilds_group.py -q` | Missing — created in this task | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

No separate Wave 0 scaffolding pass is needed — every net-new test file is created as a task WITHIN its owning plan, and each such plan is self-contained (implementation + its test in the same plan/wave). Explicitly:

- `tests/test_database_phase20.py` — NEW, created in 20-01-T2 (live-DB blocklist CRUD + silenced round-trip + blocklist-survives-config-purge). Autonomous gate: `pytest tests/test_database_phase20.py --collect-only` needs no DB.
- `tests/test_gemini_service.py` — NEW (grep for a pre-existing `test_gemini*.py` first and extend if present), created in 20-03-T3 (per-guild counter semantics; None-not-counted; embed-untagged).
- `tests/test_guilds_group.py` — NEW, created in 20-07-T3 (structural invariants: six-subcommand set, inline is_owner gate, guild_id parse guard, get_guild/teardown source tokens).
- `tests/test_guild_config_logic.py` — additive (20-02): silenced branch + decide_interaction_allowed coverage.
- `tests/test_guild_config_service.py` — additive (20-04): _blocked set load/push-invalidate + silence write-through + independent fail-open.
- `tests/test_proactive_events.py` — additive + **known regression surface** (20-05-T3): every mocked `bot.guild_config.get` mapping omits `silenced`, and the new `config_row.get("silenced", False)` branch defaults False, so existing assertions stay green; the silenced-mid-flight case is added explicitly. This is a call-site-inventory fix, not net-new scaffolding.

Nyquist: no 3 consecutive tasks lack an `<automated>` verify — all 17 tasks carry one.

---

## Manual-Only Verifications

Parked live-Discord checks (no always-on residential host — resume per the Phase 11/13/14/15/16/17 precedent). To be captured in `20-HUMAN-UAT.md` at phase close.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `/guilds list` renders every guild sorted by session AI usage (hog first), paginated + ephemeral | OWNER-01, RATE-01 | Needs a real multi-guild fleet + real Gemini traffic to see the sort/paging/usage populate | As owner, drive a few `/ask` calls in two guilds, run `/guilds list`, confirm the higher-usage guild is line one and the copy-pasteable id/flags/member-count render correctly |
| Silence takes effect on the very next event — no stale in-flight ambient response slips through | OWNER-02, OWNER-06 (SC-2) | Requires racing a real seconds-long Gemini round-trip against a live `/guilds silence` | Trigger an ambient roast/vision path, `/guilds silence <gid>` during the round-trip, confirm nothing posts; then confirm the next ambient event stays silent |
| Non-owner in a silenced guild sees the in-persona ephemeral refusal, not Discord's generic "interaction failed" | OWNER-05, OWNER-06 (D-12) | Discord client rendering of the ephemeral refusal is only observable live | In a silenced guild, run any slash command as a non-owner; confirm the sarcastic one-liner appears ephemerally, no generic failure state |
| `/guilds block` force-leaves and a real re-invite is refused (bot leaves immediately) | OWNER-03, OWNER-04 | Requires a real second guild + a real re-invite via OAuth | `/guilds block <gid>` in a test guild; re-invite the bot; confirm it leaves on join and the owner sees no false "joined" notice |
| Live-DB blocklist/silenced tests execute (not just skip) | OWNER-04, OWNER-02 | Depends on a pgvector-enabled Postgres; local dev without `TEST_DATABASE_URL` skips | Confirm CI's `pgvector/pgvector:pg16` job runs `tests/test_database_phase20.py` live (green), or run locally with `TEST_DATABASE_URL` set |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (net-new test files created within their owning plans)
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved
