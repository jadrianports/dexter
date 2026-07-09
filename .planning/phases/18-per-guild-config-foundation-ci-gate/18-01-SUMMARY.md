---
phase: 18-per-guild-config-foundation-ci-gate
plan: 01
subsystem: testing
tags: [ruff, lint, format, ci-prep, python]

# Dependency graph
requires: []
provides:
  - "pyproject.toml with [tool.ruff] config (target-version py311, line-length 120, select E/F/W/I)"
  - "requirements-dev.txt pinning ruff>=0.15,<0.16 (dev-only)"
  - "A ruff-clean, ruff-formatted ~10k-LOC repo — every subsequent Phase 18 commit lands on already-clean files"
affects: [18-02, 18-03, 18-04, 18-05, 18-06, 18-07]

# Tech tracking
tech-stack:
  added: ["ruff>=0.15,<0.16 (dev-only lint+format tool, replaces flake8+isort+black — none of which existed in this repo before)"]
  patterns:
    - "Lint/format cleanup kept as its own atomic commit, fully separate from any config-seam/feature commit (D-16)"
    - "Manual F841/E501 fixes use smallest-correct-edit (remove dead assignment, wrap long line/string) — never a blanket # noqa suppression"

key-files:
  created: [pyproject.toml, requirements-dev.txt]
  modified:
    - "80 tracked *.py files (mechanical ruff check --fix + ruff format pass; see Task Commits for the manual-fix subset)"

key-decisions:
  - "Task 1 (Ruff package-legitimacy checkpoint) was pre-approved by the user before this executor ran; treated as satisfied, no re-prompt (see Deviations)."
  - "pyproject.toml/requirements-dev.txt committed separately from the mechanical reformat, so the cleanup commit contains ONLY formatting/import-order changes plus nothing else — satisfies D-16's atomicity requirement even more strictly than 'the two config files may be folded in.'"
  - "43 findings that ruff --fix could not auto-repair (11 F841 unused-variable, 32 E501 line-too-long) were fixed by hand with the smallest correct edit — dead-code removal for F841, line-wrapping (adjacent-string-literal concatenation, backslash line-continuation, or parenthesized multi-line calls) for E501 — preserving exact runtime string content in every personality-line/prompt case touched."

patterns-established:
  - "Ruff (check + format) is now the repo's single lint/format tool, near-default ruleset (E/F/W/I), tightened later per D-14."

requirements-completed: [CICD-01]

# Metrics
duration: 40min
completed: 2026-07-10
---

# Phase 18 Plan 01: Ruff Adoption & Repo-Wide Lint/Format Cleanup Summary

**Adopted Ruff as the single lint+format tool via a new `pyproject.toml`/`requirements-dev.txt`, then brought all ~10k LOC to zero `ruff check`/`ruff format --check` findings in one atomic mechanical commit, with zero test regressions (848 pass/108 skip/0 fail, 956 collected — unchanged baseline).**

## Performance

- **Duration:** ~40 min
- **Started:** 2026-07-10 (session start)
- **Completed:** 2026-07-10T04:25:10+08:00
- **Tasks:** 3 (1 pre-approved checkpoint + 2 auto)
- **Files modified:** 82 (2 new config files + 80 reformatted tracked `*.py` files)

## Accomplishments
- `pyproject.toml` `[tool.ruff]` / `[tool.ruff.lint]` / `[tool.ruff.lint.per-file-ignores]` / `[tool.ruff.format]` tables created, matching the research-verified near-default ruleset (target-version py311, line-length 120, select E/F/W/I, `tests/*.py` F401-ignored).
- `requirements-dev.txt` pins `ruff>=0.15,<0.16` (dev-only; runtime `requirements.txt` untouched).
- Repo-wide `ruff check . --fix` (113 auto-fixed: 101 import-sort, 8 unused-import, 2 f-string-placeholder, 1 redefined-while-unused) + manual fixes for the 43 remaining findings (11 unused-variable, 32 line-too-long) + `ruff format .` (74 files reformatted, 29 already clean) — all landed in ONE mechanical commit, kept strictly separate from the config-file commit and from any future config-seam code.
- `ruff check .` and `ruff format --check .` both exit 0 on the whole repo.
- Full pytest suite confirmed byte-identical to the pre-cleanup baseline: 956 collected, 848 passed, 108 skipped, 0 failed.

## Task Commits

1. **Task 1: Package legitimacy gate — approve Ruff before install** — no commit (checkpoint; pre-approved by user before this executor ran, see Deviations)
2. **Task 2: Create Ruff config + dev-requirements** - `5c5314b` (chore)
3. **Task 3: Repo-wide lint/format cleanup — one atomic commit** - `8353d3f` (style)

**Plan metadata:** commit pending (this SUMMARY + STATE/ROADMAP update)

## Files Created/Modified
- `pyproject.toml` - New. `[tool.ruff]` config: py311 target, 120 line-length, E/F/W/I ruleset, per-file F401 ignore for `tests/*.py`, default (black-compatible) format table.
- `requirements-dev.txt` - New. Single line: `ruff>=0.15,<0.16`.
- 80 tracked `*.py` files - Mechanical `ruff check --fix` + `ruff format` pass (import sorting, whitespace/quote-style normalization). A subset of 10 files also received hand-written fixes for findings `--fix` could not auto-repair:
  - `cogs/music.py` - removed 2 dead-assignment locals (F841), wrapped 3 long lines (E501: function signature, f-string, log call)
  - `scripts/memory_spike.py` - removed 1 dead-assignment local (F841)
  - `config.py` - wrapped 13 long inline-comment lines (E501) onto a preceding comment line; zero semantic/value changes
  - `personality/prompts.py` - wrapped 1 long few-shot exemplar line via backslash line-continuation inside the triple-quoted prompt (verified byte-identical rendered string)
  - `personality/roasts.py` - wrapped 6 long roast-template string literals via adjacent-string-literal concatenation (verified byte-identical concatenated content)
  - `tests/test_audio.py`, `tests/test_database_phase11.py`, `tests/test_health_endpoint.py`, `tests/test_lyrics.py`, `tests/test_queue.py` (x3), `tests/test_tasks.py` - removed 7 dead-assignment locals (F841)
  - `tests/test_autoqueue_validate.py`, `tests/test_lyrics_lrclib.py`, `tests/test_memory.py`, `tests/test_seasonal.py`, `tests/test_taste_logic.py` (x4) - wrapped 8 long lines (E501: trailing comment relocation, multi-line string, multi-line call args, parenthesized boolean chain)

## Decisions Made
- Task 1's package-legitimacy checkpoint was already presented to and approved by the user ("approved") before this executor ran — treated as satisfied without re-prompting, per orchestrator instruction.
- Ruff was already installed locally (0.15.20, satisfies the `>=0.15,<0.16` pin) at execution start, confirming the research's Environment Availability finding; `pip install "ruff>=0.15,<0.16"` was still run (idempotent, "Requirement already satisfied").
- Split Task 2's two new config files into their own commit rather than folding them into Task 3's mechanical commit — the plan's acceptance criteria permits either, and keeping them separate makes the mechanical-cleanup commit's diff *exclusively* formatting/import-order noise (stricter than required, no downside).
- For every manual E501/F841 fix touching a string literal Dexter actually sends to Discord (personality templates, the few-shot prompt exemplar), verified the wrapped/split form is byte-identical to the original via adjacent-string-literal concatenation or backslash line-continuation — never altered wording, punctuation, or spacing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Checkpoint 1 treated as pre-satisfied, not re-executed**
- **Found during:** Task 1
- **Issue:** Task 1 is a `checkpoint:human-verify` gate that would normally halt execution and return control to the user. The orchestrator's prompt context stated this gate was already presented and the user already responded "approved" in a prior turn.
- **Fix:** Did not re-present the checkpoint or halt; proceeded directly to Task 2 per explicit orchestrator instruction, and documented the approval here for traceability.
- **Files modified:** None (process-only).
- **Verification:** N/A — instruction-following, not a code change.
- **Committed in:** N/A (no commit for a checkpoint task).

**2. [Rule 1 - Bug] 11 additional F841 unused-variable findings required hand-fixing beyond `--fix`'s automatic scope**
- **Found during:** Task 3
- **Issue:** `ruff check . --fix` does not auto-remove unused-variable assignments (F841 has no safe auto-fix in Ruff by design — removing an assignment can occasionally change behavior if the RHS has a side effect, so Ruff requires human judgment). 11 dead-assignment locals remained after `--fix`.
- **Fix:** Inspected each of the 11 call sites individually, confirmed the RHS expression's return value was never read anywhere in the enclosing scope (via full-function reads, not assumption), then removed the assignment while keeping the call/expression for its side effect (e.g. `count = cog._do_shuffle(queue)` → `cog._do_shuffle(queue)`). One case (`scripts/memory_spike.py::avg_dedup`) was a genuinely dead computation with no downstream use and was deleted outright.
- **Files modified:** `cogs/music.py`, `scripts/memory_spike.py`, `tests/test_audio.py`, `tests/test_database_phase11.py`, `tests/test_health_endpoint.py`, `tests/test_lyrics.py`, `tests/test_queue.py`, `tests/test_tasks.py`.
- **Verification:** `ruff check . --select F841` → "All checks passed!"; full suite re-run afterward confirmed 0 regressions.
- **Committed in:** `8353d3f` (Task 3 commit).

**3. [Rule 1 - Bug] 32 E501 line-too-long findings required hand-fixing beyond `--fix`'s automatic scope**
- **Found during:** Task 3
- **Issue:** Ruff's `--fix` never rewrites line length (no safe mechanical fix exists for E501 — wrapping requires human judgment about where a line can break without altering meaning). 32 lines exceeded the 120-char `line-length` config across `config.py` (13), `cogs/music.py` (3), `personality/prompts.py` (1), `personality/roasts.py` (6, one revealed only after the first pass shifted line numbers), and 5 test files (9).
- **Fix:** Applied the smallest correct edit per line: long trailing comments moved to a preceding comment line (`config.py`); long string literals split via adjacent-string-literal auto-concatenation, verified byte-identical (`personality/roasts.py`, several tests); the one triple-quoted prompt exemplar split via backslash line-continuation, verified byte-identical (`personality/prompts.py`); long function signatures/log calls/asserts reformatted across multiple lines with parentheses (`cogs/music.py`, `tests/test_seasonal.py`, `tests/test_memory.py`). No `# noqa` suppressions used anywhere.
- **Files modified:** `config.py`, `cogs/music.py`, `personality/prompts.py`, `personality/roasts.py`, `tests/test_autoqueue_validate.py`, `tests/test_lyrics_lrclib.py`, `tests/test_memory.py`, `tests/test_seasonal.py`, `tests/test_taste_logic.py`.
- **Verification:** `ruff check . --select E501` → "All checks passed!"; grep confirmed no test hardcodes the exact original long-line text; full suite re-run confirmed 0 regressions.
- **Committed in:** `8353d3f` (Task 3 commit).

---

**Total deviations:** 3 (1 process/instruction-following, 2 auto-fixed bugs within Task 3's own explicit scope)
**Impact on plan:** All three deviations were anticipated by the plan itself (Task 3's `<action>` explicitly calls for "manually resolve any residual `ruff check .` findings that `--fix` could not auto-repair... with the smallest correct edit"). No scope creep — no config-seam code touched, no new dependencies, no behavior change to any shipped feature.

## Issues Encountered
None beyond the expected manual-fix work described above. The full pytest suite (`pytest -q`, 423s) and `pytest --collect-only -q` both confirmed the mechanical reformat regressed nothing: 956 collected / 848 passed / 108 skipped / 0 failed, matching the v1.3-close baseline exactly.

## User Setup Required
None - no external service configuration required. Ruff is a dev-only tool; `requirements.txt` (runtime) is untouched.

## Next Phase Readiness
- The repo is now `ruff check`/`ruff format --check` clean — every subsequent Phase 18 plan (18-02 through 18-06's config-seam work, 18-07's CI workflow) lands on already-formatted files with zero formatting noise in its diff, exactly as D-16 intended.
- `pyproject.toml` and `requirements-dev.txt` are in place for 18-07's CI workflow to consume directly (`pip install -r requirements-dev.txt` / `ruff check .` / `ruff format --check .`).
- No blockers. The `tests/conftest.py` pgvector-codec fixture gap (Open Question 2 in 18-RESEARCH.md) is explicitly NOT this plan's job — it belongs to whichever later Phase 18 plan wires the CI service container, per the research's own sequencing note.

---
*Phase: 18-per-guild-config-foundation-ci-gate*
*Completed: 2026-07-10*

## Self-Check: PASSED

- FOUND: pyproject.toml
- FOUND: requirements-dev.txt
- FOUND: .planning/phases/18-per-guild-config-foundation-ci-gate/18-01-SUMMARY.md
- FOUND: 5c5314b (chore(18-01): add Ruff config and dev-requirements pin)
- FOUND: 8353d3f (style(18-01): adopt ruff, format repo)
- FOUND: 99b37b4 (docs(18-01): add plan 01 SUMMARY)
