---
phase: 23-portfolio-surface-ci-cd
plan: 07
subsystem: infra
tags: [readme, playwright, ffmpeg, github-actions, badges, mermaid, invite-drift-guard, honesty]

# Dependency graph
requires:
  - phase: 23-portfolio-surface-ci-cd (plan 23-04)
    provides: "ci.yml/pages.yml/release.yml three-workflow topology, the CI badge's target workflow filename"
  - phase: 23-portfolio-surface-ci-cd (plan 23-06)
    provides: "site/src/data/demo-transcript.ts (BLOCKED, placeholder tokens), site/dist/index.html built artifact"
  - phase: 22-invite-plumbing
    provides: "logic/invite.py::build_invite_url(), tests/test_invite_drift_guard.py"
provides:
  - "scripts/render_demo_gif.py — validated Playwright-video + ffmpeg-palette GIF pipeline, blocked on real demo lines"
  - "README.md rewritten as an architecture case study (PORT-03/PORT-04)"
  - "tests/test_invite_drift_guard.py proven NON-VACUOUS for the first time (README.md now in its scanned set, canonical URL found, zero offenders)"
  - "23-HUMAN-UAT.md — the phase's complete acknowledged-deferred ledger (9 items)"
affects: [milestone-close]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "GIF-pipeline validated against a scratch output before deciding whether to commit the real artifact — proves the mechanism without shipping a dishonest one"

key-files:
  created:
    - scripts/render_demo_gif.py
    - .planning/phases/23-portfolio-surface-ci-cd/23-HUMAN-UAT.md
  modified:
    - README.md
    - tests/test_site_drift_guard.py

key-decisions:
  - "docs/demo.gif is deliberately NOT rendered/committed this plan — site/src/data/demo-transcript.ts still carries {{DEXTER_DEMO_LINE_1/2}} placeholder tokens (23-DEMO-TRANSCRIPT.md BLOCKED, deferred by the user 2026-07-14). Rendering the current build would ship a public, permanently-cached asset visibly showing placeholder tokens on a page whose entire thesis is honest disclosure — a worse failure mode than no GIF. Overrides the plan's literal 'docs/demo.gif exists' acceptance line per the orchestrator's explicit honesty-first critical_notes."
  - "README's demo section references docs/demo.gif with an honest pending-status note (links to 23-HUMAN-UAT.md and the live landing page) instead of an <img>/markdown-image embed of a nonexistent file — same honesty override."
  - "README boundary 4 (hybrid memory scoping) paraphrases PROJECT.md's shipped Key Decisions wording, explicitly naming /ask as global-but-self-scoped, matching Phase 21's own flagged requirement (STATE.md decision log, Phase 21-04)."
  - "Fixed a pre-existing ruff format drift in tests/test_site_drift_guard.py (from plan 23-03, mechanical line-unwrap) — blocked this task's required 'ruff check . && ruff format --check .' final gate."

requirements-completed: []  # PORT-02/CICD-02/CICD-03 intentionally NOT marked — see Deviations / HUMAN-UAT. PORT-03/PORT-04 are code-complete; REQUIREMENTS.md left untouched per explicit instruction (orchestrator reconciles).

# Metrics
duration: 35min
completed: 2026-07-14
---

# Phase 23 Plan 07: README Case Study + Honest Demo-GIF Deferral Summary

**Rewrote the two-line README into a five-badge, mermaid-diagrammed, four-boundary architecture case study whose invite link makes Phase 22's drift guard non-vacuous for the first time — and, on discovering the demo transcript is still placeholder-gated, wrote and validated the GIF-render pipeline without shipping a GIF that would visibly show `{{DEXTER_DEMO_LINE_*}}` tokens.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-07-14T12:57Z
- **Tasks:** 3 (all type="auto")
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments

- `scripts/render_demo_gif.py` written: Playwright browser-context video recording (not a
  screenshot loop — CSS animations must play naturally) of `site/dist/index.html`'s demo mock,
  converted via a two-pass ffmpeg `palettegen`/`paletteuse` pipeline (12fps, 640px wide, lanczos
  scaling). **Validated end-to-end this session** against a scratch output: recorded a real
  `.webm` from the current build and converted it to a 0.95MB GIF — well under the 2MB budget —
  proving the mechanism works, then discarded the scratch output.
- **Discovered the demo transcript is still `BLOCKED`** (23-DEMO-TRANSCRIPT.md, deferred by the
  user 2026-07-14) — `site/src/data/demo-transcript.ts` still carries both
  `{{DEXTER_DEMO_LINE_1}}` / `{{DEXTER_DEMO_LINE_2}}` placeholder tokens verbatim. Per the
  orchestrator's explicit critical_notes, did **not** render/commit `docs/demo.gif` — doing so
  would ship a public, permanently-cached README asset visibly showing placeholder tokens, which
  is a worse failure mode than shipping no GIF on a page whose entire thesis is honest disclosure.
- `README.md` fully rewritten (2 lines → ~180 lines): tagline (Dexter quoted, D-09) → 5 badges
  (CI status referencing `ci.yml` by filename + 4 shields.io tech badges, zero license badge per
  D-15) → an honest demo-pending note → feature list (explicitly calling out the 5-button
  now-playing panel the demo can't show) → a `mermaid graph TD` of the cog/service/logic/
  persistence layering → 4 hard-problem callouts (RAG-on-zero-new-infra, `_play_generation`
  counter, accuracy firewall, two-choke-point kill-switch) → 4 honest boundaries (100-guild wall,
  on-demand hosting, full-savage + reactive kill-switch, hybrid memory scoping) → the canonical
  invite link.
- **Proved `tests/test_invite_drift_guard.py` is now non-vacuous, not just green**: directly
  invoked `_collect_offenders(_tracked_doc_files(root), _canonical_url())` and confirmed
  `README.md` is genuinely in the scanned file set, the canonical URL is found verbatim inside
  it, and zero offenders are reported. This is Phase 22's guard enforcing something real for the
  first time since it was written.
- `.planning/phases/23-portfolio-surface-ci-cd/23-HUMAN-UAT.md` written: 9 numbered items
  covering every parked dependency across the whole phase (real demo lines, the downstream GIF
  render, the GitHub Pages source toggle + its first real run, the GHCR visibility flip + its
  first real run, README GitHub-rendering, the CI badge's green-at-true-HEAD proof, and the
  landing-page visual/copy review) — each marked honestly as done-with-evidence or blocked,
  never quietly passed.
- Fixed a pre-existing `ruff format` drift in `tests/test_site_drift_guard.py` (from plan
  23-03 — a single multi-line `pytest.fail(...)` call, mechanical line-unwrap only) that was
  blocking this task's required final gate.
- **Final gates confirmed green:** `ruff check .` and `ruff format --check .` both clean
  repo-wide; full suite `1039 passed, 124 skipped, 0 failed` in 422.83s (no local Postgres —
  matches the expected DB-unavailable skip pattern); `tests/test_invite_drift_guard.py` (9/9) and
  `tests/test_site_drift_guard.py` (3/3, `SITE_DIST_REQUIRED=1`) both green.

## Task Commits

Each task was committed atomically:

1. **Task 1: Render docs/demo.gif from the landing page's mock (D-07)** — `a668988` (feat) —
   wrote and validated `scripts/render_demo_gif.py`; did **not** commit `docs/demo.gif` (blocked,
   see Deviations)
2. **Task 2: Rewrite README.md as an architecture case study (PORT-03/PORT-04)** — `18667bb`
   (feat)
3. **Task 3: Write 23-HUMAN-UAT.md and close the phase honestly (D-17, CICD-03)** — `91b971f`
   (docs) — also carries the `tests/test_site_drift_guard.py` ruff-format fix

**Plan metadata:** (this commit, following SUMMARY)

## Files Created/Modified

- `scripts/render_demo_gif.py` — Playwright video capture + two-pass ffmpeg palette conversion;
  dev-machine-only, documented one-time setup, never in CI; validated end-to-end against a
  scratch output this session
- `README.md` — full rewrite, 2 lines → architecture case study
- `.planning/phases/23-portfolio-surface-ci-cd/23-HUMAN-UAT.md` — the phase's acknowledged-deferred ledger, 9 items
- `tests/test_site_drift_guard.py` — mechanical `ruff format` fix (line-unwrap only, no logic change)

## Decisions Made

- **docs/demo.gif deliberately withheld.** The plan's Task 1 acceptance criteria call for a
  committed `docs/demo.gif` ≤2MB; the orchestrator's critical_notes explicitly instruct writing
  and validating the script without rendering a GIF that would show placeholder tokens. Chose
  honesty over literal task completion — this is the entire thesis of the phase (PORT-04, T-23-HONEST).
  Documented as the single item in 23-HUMAN-UAT.md that both PORT-02 and this GIF depend on.
- **README's demo section uses a pending-status note, not a broken image embed.** An
  `![...](docs/demo.gif)` markdown-image reference to a file that doesn't exist would render as a
  broken image on GitHub — dishonest presentation on a document whose stated purpose is
  professional engineering signal. Wrote prose instead, referencing the live landing page and
  `23-HUMAN-UAT.md`.
- **Boundary 4 cross-checked against PROJECT.md's shipped wording, not the hypothesis** — named
  `/ask` explicitly as global-but-self-scoped, matching the exact concern Phase 21's own STATE.md
  decision log flagged for this phase (an imprecise row omitting `/ask` would make the disclosure
  false).
- **Fixed the pre-existing `tests/test_site_drift_guard.py` ruff drift** rather than deferring it
  — it directly blocked this task's own required "final gates all green" acceptance criterion,
  and the fix is a single mechanical line-unwrap with no logic change (same category as the
  Phase 23-01 precedent).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed a pre-existing `ruff format` drift in `tests/test_site_drift_guard.py`**
- **Found during:** Task 3 (running the "final gates all green" verification)
- **Issue:** A single multi-line `pytest.fail(...)` call (from plan 23-03) violated the
  project's configured line length after a prior edit; `ruff format --check .` failed on this
  one file, blocking the phase-close gate this task's acceptance criteria require.
- **Fix:** Ran `ruff format tests/test_site_drift_guard.py`; diff reviewed and confirmed purely
  mechanical (a two-line string literal joined onto one line, no logic change).
- **Files modified:** `tests/test_site_drift_guard.py`
- **Verification:** `ruff format --check .` now passes repo-wide; re-ran
  `SITE_DIST_REQUIRED=1 pytest tests/test_site_drift_guard.py` (3/3 still pass).
- **Committed in:** `91b971f` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug), plus 1 deliberate, explicitly-instructed
non-conformance to the plan's literal Task 1 acceptance line (docs/demo.gif not committed —
this is not an auto-fix under Rules 1-3; it is a direct honesty-first override from the
orchestrator's critical_notes, documented above under Decisions Made and in 23-HUMAN-UAT.md).
**Impact on plan:** No scope creep. The ruff fix was necessary for the phase-close gate; the
GIF deferral is the correct, instructed behavior given the upstream transcript is still blocked.

## Issues Encountered

None beyond the two items above (both resolved as described).

## User Setup Required

**23-HUMAN-UAT.md carries the full phase-level ledger** (9 items — see that file for exact
steps and current status). The item this plan directly produced or depends on:
- Supply two verbatim, real Dexter lines into `23-DEMO-TRANSCRIPT.md`, then copy them
  byte-for-byte into `site/src/data/demo-transcript.ts` (PORT-02, deferred by the user
  2026-07-14). Once done: `cd site && npm ci && npm run build` then
  `python scripts/render_demo_gif.py` produces `docs/demo.gif`.

## Next Phase Readiness

- All three tasks complete and committed locally (no push — orchestrator performs the
  consolidated phase-end push).
- README.md, `scripts/render_demo_gif.py`, and `23-HUMAN-UAT.md` are all in place; the invite
  drift guard is proven non-vacuous.
- `docs/demo.gif` and the transcript it depends on are the one thing genuinely blocking PORT-02
  and part of PORT-03's full realization — tracked, not silently skipped.
- CICD-02/CICD-03's real-run proofs remain deferred to the orchestrator's consolidated push
  (per 23-04's own deferral) plus two manual UI steps (Pages source toggle, GHCR visibility
  flip) neither of which this plan's file scope can perform.
- `.planning/REQUIREMENTS.md` left untouched, per explicit instruction — the orchestrator
  reconciles PORT-01…04/CICD-02/03 completion during phase verification, using
  `23-HUMAN-UAT.md` as the evidence ledger.

---
*Phase: 23-portfolio-surface-ci-cd*
*Completed: 2026-07-14*

## Self-Check: PASSED

All 4 created/modified files (`scripts/render_demo_gif.py`, `README.md`,
`.planning/phases/23-portfolio-surface-ci-cd/23-HUMAN-UAT.md`, `tests/test_site_drift_guard.py`)
and all 3 task commit hashes (`a668988`, `18667bb`, `91b971f`) confirmed present via filesystem
checks and `git log --oneline --all`.
