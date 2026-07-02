# Phase 15: RAG Reach - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-03
**Phase:** 15-rag-reach
**Areas discussed:** Recall cadence (RAG-01/02), /memory view (RAG-03), /memory forget granularity (RAG-04)

**Scouting finding that framed the whole discussion:** RAG-01 and RAG-02 are already
wired in Phase 11 (`cogs/ai.py` — target-scoped `/roast` recall + invoker-scoped `/ask`
recall), both gated behind `MEMORY_CALLBACK_CHANCE` (0.35). The genuinely new work is
`/memory` (RAG-03) + `/memory forget` (RAG-04). This was surfaced to the user up front.

---

## Recall cadence for explicit `/roast` & `/ask` (RAG-01 / RAG-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Always ground explicit cmds | Drop the 0.35 gate for /roast + /ask; rely on the 0.70 similarity floor + model NOOP. Keep the gate on ambient roasts only. Byte-identical fallback preserved. | ✓ (Claude rec, adopted on user's behalf) |
| Keep occasional gate | Leave the 0.35 gate everywhere; RAG-01/02 verify-only, no behavior change. | |

**User's choice:** User asked to discuss the tradeoff and for Claude's educated
recommendation, then re-ask. Claude recommended **Always ground explicit commands**. User
stepped away before answering the re-ask; recommendation adopted on their behalf (D-01),
flagged for revision.
**Notes:** Rationale — explicit commands are opted-in, so a 65%-chance no-op reads as
flaky; the similarity floor (0.70) already provides the "when relevant" gate and injected
memories remain candidate ammo the model may NOOP, so quality is protected without the
random gate. Rarity-hits-harder (Phase 11 D-04) still applies to *ambient/unprompted*
surfaces, which keep the gate.

---

## `/memory` view — content & visibility (RAG-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Verbatim facts, Dex framing | List the actual stored fact strings with a short in-character intro/outro. Best for a trust escape hatch — you see exactly what will be forgotten. | ✓ |
| Gemini paraphrase | Show an in-character rewritten summary. More alive but can distort/hide what's actually stored. | |
| Discuss content + visibility | Talk through fields, empty-state, ephemeral-vs-public. | |

**User's choice:** **Verbatim facts, Dex framing** (locked directly, first pass).
**Notes:** Chosen as a transparency/trust surface — the user must see exactly what is
stored (and therefore what `/memory forget` erases). View is read-only + ephemeral;
empty state is in-character. Field/pagination detail left to planner (Open Question 1).

---

## `/memory forget` — granularity & safety (RAG-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Nuke-all + confirm | Wipe all invoker memories behind an ephemeral confirm w/ count preview. Clean verifiable escape hatch; DJ re-distills from untouched song_history. | ✓ (Claude rec, adopted on user's behalf) |
| Kind-aware forget | Support "forget everything" AND "keep taste / drop roast ammo". Preserves DJ, adds selector + test surface. | |
| Per-item selective | Numbered view + forget by index. Most surgical, highest complexity + bug surface. | |

**User's choice:** User asked to discuss the tradeoffs across all options and for Claude's
educated recommendation, then re-ask. Claude recommended **Nuke-all + confirm**. User
stepped away before answering the re-ask; recommendation adopted on their behalf (D-03),
flagged for revision.
**Notes:** Key insight — forget deletes the *memory vector store*, not the underlying
`song_history` play logs, so the taste brain re-distills gracefully; nuke-all isn't as
destructive to the DJ as it first appears. The escape hatch stays clean/total/verifiable
(what Phase 16 hard-depends on) at the lowest bug risk on the one path where a bug is
catastrophic (deletion). Selective/kind-aware deferred to backlog — layers on later
without rework.

## Claude's Discretion

- Command surface shape (`/memory` group + view/forget subcommands vs. cog placement).
- `/memory` view rendering fields + pagination (reuse `QueuePageView`/`LyricsPageView`).
- Confirmation UX specifics (labels, timeout) — reuse the 14-04/14-05 confirm-view pattern.

## Deferred Ideas

- Kind-aware / selective / per-item `/memory forget` → backlog.
- Owner/mod forgetting *another* user's memory → out of scope (self-scoped only).
- Proactive unprompted callbacks + opt-out → Phase 16.
- Vision / multimodal roasting → Phase 17.
