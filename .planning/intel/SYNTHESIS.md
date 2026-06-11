# Synthesis Summary

> Entry point for `gsd-roadmapper`. Produced by `gsd-doc-synthesizer` from per-doc classifications + sources.
> Mode: new (bootstrap). No existing PROJECT.md / REQUIREMENTS.md / ROADMAP.md.

## Doc counts by type

- Total ingested: 6
- SPEC: 3
  - docs/superpowers/specs/2026-04-12-dexter-phase1-design.md
  - docs/superpowers/specs/2026-04-13-dexter-phase2-design.md
  - docs/superpowers/specs/2026-06-02-dexter-phase2.5-hardening-design.md
- DOC: 3
  - docs/superpowers/plans/2026-04-12-dexter-phase1-mvp.md
  - docs/superpowers/plans/2026-04-13-dexter-phase2-personality-ai.md
  - docs/superpowers/plans/2026-06-02-dexter-phase2.5-hardening.md
- ADR: 0
- PRD: 0

The three SPEC/DOC pairs are **sequential project phases** (1 → 2 → 2.5), not competing designs of the same scope. Each plan (DOC) cross-references its sibling design (SPEC).

## Decisions locked

- Count: 0. No ADRs and no `locked: true` documents in the set.
- "Decisions Made" / "Architecture Decisions" tables inside the SPECs were extracted as constraints, not locked ADR records (per classifier).

## Requirements extracted

- Count: 0 PRD-derived requirements (no PRDs ingested).
- Requirement-shaped intent must be derived downstream from constraints + context. No `REQ-*` units, no competing PRD acceptance variants.

## Constraints

- File: intel/constraints.md
- Count: 14 constraint entries across 3 SPECs.
  - Phase 1 (6): C-P1-ARCH (protocol), C-P1-SCHEMA (schema), C-P1-AUDIO (protocol), C-P1-QUEUE (protocol), C-P1-NFR (nfr), C-P1-DEFER (nfr)
  - Phase 2 (5): C-P2-GEMINI (api-contract), C-P2-MODEL (nfr), C-P2-AUTOQUEUE (protocol), C-P2-DB (api-contract), C-P2-INFRA (protocol)
  - Phase 2.5 (4): C-P25-SCOPE (nfr), C-P25-OBS (protocol), C-P25-FIX (protocol), C-P25-TEST (nfr)
- Type breakdown: protocol 6, nfr 5, api-contract 2, schema 1.

## Context topics

- File: intel/context.md
- Count: 4 topics (Phase 1 build plan, Phase 2 build plan, Phase 2.5 hardening build plan, recent-commit alignment reference).

## Conflicts

- Blockers: 0
- Competing variants (WARNINGS): 1 — divergent image-generation model across two equal-precedence SPECs (precedence cannot break the tie).
- Auto-resolved (INFO): 2 — SPEC > DOC on image-model scope; Phase 2.5 int-bind correction recorded as evolution (not contradiction).
- Detail: see ../INGEST-CONFLICTS.md

## Pointers

- Decisions (ADR intel): intel/decisions.md (empty — no ADRs)
- Requirements (PRD intel): intel/requirements.md (empty — no PRDs)
- Constraints (SPEC intel): intel/constraints.md
- Context (DOC intel): intel/context.md
- Conflicts report: ../INGEST-CONFLICTS.md

## Routing note for roadmapper

STATUS: AWAITING USER — one competing variant (image-gen model) should be resolved before routing. There are zero blockers, so synthesis is otherwise complete and the constraint/context intel is safe to consume.
