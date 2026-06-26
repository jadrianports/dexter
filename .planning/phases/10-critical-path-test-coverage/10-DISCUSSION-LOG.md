# Phase 10: Critical-Path Test Coverage - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-27
**Phase:** 10-Critical-Path Test Coverage
**Areas discussed:** Seam home, Refactor risk, Input seam, Regression gate, Coverage depth, Scar tests

---

## Seam home (where extracted pure functions live)

| Option | Description | Selected |
|--------|-------------|----------|
| Module-level in each cog | Co-locate pure functions at module level in the cog files (matches the existing `gather_bot_metrics` precedent). Lowest churn. | |
| New `logic/` package | Dedicated `logic/playback.py`, `health.py`, `roasts.py`; clearest pure-vs-glue boundary; Phase 11 imports from the same package. | ✓ |
| You decide | Planner picks based on import-cycle / cohesion analysis. | |

**User's choice:** New `logic/` package
**Notes:** Tests mirror modules: `test_playback_logic.py`, `test_health_logic.py`, `test_roast_logic.py`.

---

## Refactor risk (how aggressively to refactor live cogs)

| Option | Description | Selected |
|--------|-------------|----------|
| True extraction (cog calls it) | Live cog method calls the pure function as single source of truth; thin glue dispatches on the decision. No drift. Touches shipped playback — covered by the regression gate. | ✓ |
| Mirror + test (lower risk) | Pure functions replicate the decision and are tested separately; live paths untouched. Drift risk. | |
| You decide | Planner chooses per-target. | |

**User's choice:** True extraction (cog calls it)
**Notes:** Risk of touching shipped playback accepted; TEST-04 regression gate covers it.

---

## Input seam (how pure functions receive inputs, esp. random rolls)

| Option | Description | Selected |
|--------|-------------|----------|
| Primitives + rolls as params | Plain values + random roll(s) passed in as float params; `random()` stays in glue. | |
| Snapshot dataclasses | Small frozen dataclasses bundle inputs; functions take one snapshot arg. | |
| You decide | Planner picks the shape per function. | ✓ |

**User's choice:** You decide
**Notes:** Hard constraint regardless of shape — functions must be deterministic; randomness/clocks stay in glue and are passed in.

---

## Regression gate (TEST-04 definition)

| Option | Description | Selected |
|--------|-------------|----------|
| pytest green + manual boot check | Full suite passes (automated) + manual `python bot.py` boot with `dexter.log` eyeballed for new failures. | ✓ |
| pytest green only | Suite-green is the gate; boot verification folded into normal usage. | |
| Scripted boot smoke check | A script boots far enough to wire/import everything (mocked) and asserts no errors logged. | |

**User's choice:** pytest green + manual boot check
**Notes:** Boot can't be fully automated (needs real Discord token + Neon); bot runs on user's PC on-demand, so manual boot is pragmatic.

---

## Coverage depth (how exhaustive per function)

| Option | Description | Selected |
|--------|-------------|----------|
| Full branch + boundary | Every branch and boundary enumerated (empty queue, index clamp both ends, cooldown exactly-at-ceiling, each degraded-reason combo, roll boundaries). | ✓ |
| Happy path + key edges | Main decisions + known-risky edges only; skip exhaustive permutations. | |
| You decide | Planner sets depth per function. | |

**User's choice:** Full branch + boundary (via "Other" — user: "full branch should be better wouldn't you agree?")
**Notes:** Agreed — phase exists to lock decision logic that has already shipped live bugs; pure functions make exhaustive branch testing cheap (no Discord/DB mocking), so high payoff / low cost.

---

## Scar tests (mandatory named regression cases)

| Option | Description | Selected |
|--------|-------------|----------|
| Finished-song replay | Exhausted-queue path returns STOP-and-clear so the just-finished track isn't replayed on restart. | ✓ |
| Silent auto-queue | Auto-queue-vs-stop gates on the correct ground truth (the is_playing-flag vs voice-client confusion). | ✓ |
| REL-01 degraded path | `determine_health_status` returns degraded (503 when strict) for each critical reason. | ✓ |
| Restore index clamp | Stale/non-int/out-of-range `current_index` clamped so it never reaches `_play_track(None)`. | ✓ |

**User's choice:** All four selected as mandatory
**Notes:** Each maps to a real recorded outage/misbehavior in CLAUDE.md's "Implementation Gotchas"; must be named and findable, not buried in a parametrized sweep.

---

## Claude's Discretion

- Input seam shape per function (primitives + rolls vs snapshot dataclass) — D-06.
- Exact pure/glue cut-line per target, function names/signatures, full per-function edge-case list — D-07.

## Deferred Ideas

None — discussion stayed within phase scope. (Cog/Discord-glue integration tests remain
untested-by-design; RAG pure-logic tests are Phase 11.)
