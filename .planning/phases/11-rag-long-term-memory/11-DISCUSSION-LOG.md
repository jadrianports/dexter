# Phase 11: RAG Long-Term Memory - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-29
**Phase:** 11-rag-long-term-memory
**Areas discussed:** Sensitivity line, Callback cadence, Salience source, Write triggers, /forget scope

---

## Sensitivity line (PII / sensitivity gate)

| Option | Description | Selected |
|--------|-------------|----------|
| Identity & wellbeing | Block mental health, self-harm, medical, sexuality, grief/relationship trauma, real-world PII, anything said in distress. Cringe/hypocrisy/3am binges/light drama = fair game. | ✓ |
| Only hard PII | Block only real-world identifiers; emotional/health content fair game if funny. | |
| Conservative — when in doubt, drop | Distiller errs heavily toward not storing borderline content. | |

**User's choice:** Identity & wellbeing
**Notes:** Tone target — punch at choices and hypocrisy, never at vulnerability. Stop-ship gate, ships in v1.

---

## Callback cadence

| Option | Description | Selected |
|--------|-------------|----------|
| Occasional payoff + anti-repeat | Memory surfaces as a treat, not every roast; `last_surfaced_at` + novelty penalty. Stays NOOP-able candidate ammo. | ✓ |
| Whenever it has ammo | Inject any relevant memory clearing the floor on every roast. | |
| Rare / special-occasion | Only high-salience callbacks surface. | |

**User's choice:** Occasional payoff + anti-repeat
**Notes:** This promotes anti-repeat (`last_surfaced_at` + novelty penalty) from research's "should-have v1.x" INTO Phase 11, since the cadence choice depends on it.

---

## Salience source

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid: event floor + distiller | Event type sets base weight; distiller may bump for a spicy moment. Feeds decay/eviction. | ✓ |
| Event-type weights only | Deterministic, cheap, no LLM judgment. | |
| Distiller-judged only | LLM assigns 0–1 importance per fact. | |

**User's choice:** Hybrid: event floor + distiller
**Notes:** Resolves the research-flagged "salience source" gap. Exact base-weights + bump mechanism are 11.3/11.4 implementation detail.

---

## Write triggers (distill boundary)

| Option | Description | Selected |
|--------|-------------|----------|
| Event hooks + daily batch | Notable-event hooks write immediately; once-daily batch distills banter from message buffers. No session-end path. | ✓ |
| Event hooks only | Simplest; only notable events write. Thinnest corpus. | |
| Hooks + session-end + daily batch | Also distill on last-user-leaves-voice. Richest, more triggers. | |

**User's choice:** Event hooks + daily batch
**Notes:** Resolves the research-flagged "session-end boundary" gap. Voice-session-end explicitly rejected to avoid a third write path. Never per-message.

---

## /forget owner command scope

| Option | Description | Selected |
|--------|-------------|----------|
| Defer to v1.x | Decay sweep + per-user cap already bound the store; a misfire ages out. | ✓ |
| Include in Phase 11 | Ship owner-only /forget for on-demand pruning. | |

**User's choice:** Defer to v1.x

---

## Claude's Discretion

- All numeric retrieval defaults (top-k, similarity floor, dedup threshold, per-user cap, decay
  window, rerank weights, injected-fact count/token budget) — deferred to the opening numeric-defaults
  validation spike + 11.2–11.5 observation. Research priors are the starting points.
- Exact salience base-weights per event type and the precise distiller-bump mechanism — 11.3/11.4
  implementation detail.
- All research-verified HIGH mechanics (boot ordering, codec registration, prompt-injection site,
  sweep-task pattern) — follow canonical refs, no re-litigation.

## Deferred Ideas

- `/forget` owner command → v1.x.
- Cross-user / "server lore" memory → anti-feature for now (scoping/privacy unresolved).
- Salience/novelty re-rank deep tuning beyond in-phase hybrid + anti-repeat → revisit post-spike.
- HNSW ANN index → only past ~10k rows; never IVFFlat on an empty table.
