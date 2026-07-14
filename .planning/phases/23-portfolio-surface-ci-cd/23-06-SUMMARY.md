# Plan 23-06 Summary — Content Sections + Page Composition

**Plan:** 23-06 (Wave 6) — demo mock (PORT-02), feature showcase (PORT-01), honest boundaries (PORT-04), composed single-scroll.
**Status:** Complete. (The executor built and committed Tasks 1–2 and the Task-3 components, then hit a session limit before committing the final `index.astro` composition and writing this SUMMARY; the orchestrator finished both after verifying build + drift guard + honesty gate.)

## Commits
- `12fe4fa`: feat(23-06): demo mock (PORT-02/D-06) — verbatim placeholder tokens, honesty caption
- `d513676`: feat(23-06): features showcase + honest boundaries (PORT-01/PORT-04)
- `<this wave>`: feat(23-06): compose single-scroll page in locked order (D-05) — orchestrator-finished

## What was built
- `site/src/data/demo-transcript.ts` — carries the `{{DEXTER_DEMO_LINE_1/2}}` placeholder tokens **verbatim**, with an explicit DO-NOT-AUTHOR contract in the file header. Human handle `wrenlow` + two author-able setup lines; both Dexter replies left as visible placeholders.
- `site/src/components/DemoMock.astro`, `DemoMessage.astro` — Discord-conversation reconstruction (pixels ours; words gated).
- `site/src/components/Features.astro`, `FeatureCard.astro` — feature showcase (PORT-01).
- `site/src/components/Boundaries.astro`, `BoundaryItem.astro` — honest scope boundaries (PORT-04): 100-guild verification wall, on-demand hosting caveat, full-savage-personality + reactive-kill-switch tradeoff, hybrid memory-scoping decision.
- `site/src/pages/index.astro` — composed in the locked D-05 order: **Hero → DemoMock → Features → Boundaries → Cta → Footer**.

## Verification (orchestrator, post-resume)
- `cd site && npm run build` → exits 0, 1 page built.
- `SITE_DIST_REQUIRED=1 pytest tests/test_site_drift_guard.py` → **3 passed**.
- Both demo placeholder tokens present in `dist/index.html` (2× each) — **PORT-02 correctly remains incomplete** (BLOCKED on the user's real Dexter lines).
- Canonical invite URL (`client_id=1492588698364018898`) appears exactly **2×** in `dist/index.html`; total `discord.com/oauth2/authorize` occurrences also 2 — **no rogue hand-typed URL**.
- No invented Dexter lines anywhere; no `personality/` template substitution (D-06 honored).

## Requirement status (NOT marked here — orchestrator reconciles at verification)
- **PORT-01** (landing page: hero + feature showcase + Add-to-Discord button) — structurally delivered by chassis (23-05) + features (this wave); candidate for Complete at verification.
- **PORT-04** (honest boundaries) — delivered this wave; candidate for Complete at verification.
- **PORT-02** (demo) — **incomplete / BLOCKED**: placeholder tokens still present pending the user's two real Dexter lines.

`.planning/REQUIREMENTS.md` left untouched per instruction.

## Deviations
- Plan finished by the orchestrator after an executor session-limit interruption (the only "deviation": authorship of the final compose-commit + this SUMMARY moved from executor to orchestrator; work content unchanged and independently re-verified).
