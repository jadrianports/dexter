---
phase: 22-invite-plumbing
plan: 03
subsystem: tests
tags: [pytest, git-introspection, ci, drift-guard, security]

requires:
  - phase: 22-invite-plumbing
    plan: "22-01"
    provides: "config.DISCORD_CLIENT_ID / INVITE_PERMISSIONS_VALUE / INVITE_SCOPES + logic/invite.py::build_invite_url()"
provides:
  - "tests/test_invite_drift_guard.py — CI-enforced git-tracked-doc invite-URL drift guard (T-22-02) + Python single-constructor invariant (T-22-03)"
affects: [23-portfolio-surface-ci-cd]

tech-stack:
  added: []
  patterns:
    - "Repo-introspection pytest (subprocess `git ls-files`/`git rev-parse`) — new test infrastructure for this codebase; the guard runs in the existing zero-secret CI job with no workflow change"

key-files:
  created:
    - tests/test_invite_drift_guard.py
  modified:
    - config.py
    - logic/__init__.py

key-decisions:
  - "D-10: `.planning/` excluded via a directory-prefix denylist (not a per-file allowlist), plus a `.md`/`.html`/`.txt` extension allowlist — resolves the `.planning/research/STACK.md` `<APP_ID>`-placeholder false-positive risk"
  - "`_collect_offenders(paths, canonical)` takes an explicit path list so `tmp_path`-based positive/negative controls exercise the exact same comparison logic as the real repo scan, not a reimplementation"
  - "Reworded two pre-existing prose comments (config.py INVITE_SCOPES comment, logic/__init__.py package docstring) that legitimately mentioned `oauth_url(` in documentation — not construction — because the new single-constructor scan can't distinguish prose from code; same literal-substring-avoidance discipline already used in 22-01/22-02"

requirements-completed: [INVITE-02]

duration: 25min
completed: 2026-07-14
---

# Phase 22 Plan 03: Invite URL Drift Guard Summary

**A CI-enforced pytest that git-introspects every tracked doc and Python file to make a stale, over-privileged, or duplicated invite URL structurally impossible to merge — proven not a no-op by a mandatory positive control.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 2 completed
- **Files modified:** 3 (tests/test_invite_drift_guard.py created; config.py, logic/__init__.py touched to remove two incidental marker-string false positives)

## Accomplishments

- `tests/test_invite_drift_guard.py` — 9 tests, all mock-free repo introspection via `subprocess` calls to `git ls-files` / `git rev-parse --show-toplevel`:
  - `test_no_doc_contains_a_drifted_invite_url` — THE guard (T-22-02). Scans every git-tracked, non-`.planning/`, `.md`/`.html`/`.txt` file for OAuth2 URLs and asserts literal equality with `build_invite_url()`'s output. **Confirmed passing vacuously today**: `git grep -n "oauth2/authorize" -- . ':!.planning'` returns only two prose mentions (this test file's own docstring/pattern comment and `logic/invite.py`'s docstring), neither of which is a real `?query`-bearing URL the regex matches.
  - `test_drift_guard_actually_detects_a_mismatch` — mandatory positive control (T-22-02a). Feeds `permissions=8` (literal Administrator) through the real `_collect_offenders` seam and asserts it's caught, proving the vacuous pass above isn't a false green.
  - `test_drift_guard_accepts_the_canonical_url` — paired negative control (the real URL produces zero offenders).
  - `test_scanner_matches_urls_in_markdown_html_and_bare_forms` — the canonical URL embedded as a Markdown link, HTML `href`, and bare text all extract cleanly with no trailing `)`/`"` contamination.
  - `test_planning_tree_is_excluded_from_the_scan` / `test_only_text_extensions_are_scanned` — D-10's directory-prefix denylist + extension allowlist, positively proven (`.planning/` docs exist and are tracked but absent from the scan).
  - `test_canonical_url_resolves_without_env_secrets` — D-04 CI-parity: the canonical URL resolves from `config.py`'s committed constants even with `DISCORD_CLIENT_ID` deleted from the environment.
  - `test_logic_invite_is_the_only_url_constructor` — T-22-03. Scans every git-tracked, non-`tests/`, non-`.planning/` `.py` file; only `logic/invite.py` may contain `oauth_url(` or the literal `discord.com/oauth2/authorize`.
  - `test_config_holds_no_url_literal` — `config.py` never contains a `discord.com/oauth2` literal.

## Task Commits

Each task was committed atomically:

1. **Task 1: Build the git-tracked-doc drift guard + its positive control (D-03/D-10)** - `b3fc3a3` (test)
2. **Task 2: Lock the single-constructor invariant — no second URL builder can be added (D-03/D-07)** - `b477090` (test)

## Files Created/Modified

- `tests/test_invite_drift_guard.py` — new file, 9 tests, 4 module constants (`URL_PATTERN`, `TEXT_EXTENSIONS`, `PLANNING_PREFIX`, `_CONSTRUCTOR_MARKERS`), 6 helpers (`_repo_root`, `_tracked_doc_files`, `_tracked_python_files`, `_canonical_url`, `_collect_offenders`, plus `_ALLOWED_CONSTRUCTOR`)
- `config.py` — reworded the `INVITE_SCOPES` comment ("oauth_url() takes an Iterable[str]..." → "discord.py's OAuth2 URL builder takes an Iterable[str]...") so it no longer trips the new Python-file marker scan
- `logic/__init__.py` — reworded the package-level docstring's `logic/invite.py` exception note (dropped the literal `discord.utils.oauth_url()` substring, kept the explanation) for the same reason

## Decisions Made

- Task 2's single-constructor scan (`_CONSTRUCTOR_MARKERS = ("oauth_url(", "discord.com/oauth2/authorize")`) initially flagged `config.py` and `logic/__init__.py` as false-positive offenders — both contained the literal substring `oauth_url(` in *documentation prose* (explaining discord.py's helper), not in a real second constructor. Rather than weaken the scan (e.g. stripping comments, which would open a real hole — a future second constructor could just be commented as "not really a call"), reworded the two prose comments to describe the same thing without the literal substring. This mirrors the exact discipline 22-01 and 22-02 already established in this same phase (keeping `grep -c` acceptance checks exact by avoiding literal substrings in explanatory prose) — not a new pattern, a continuation of one.
- Kept `_collect_offenders` as an explicit-path-list function (per the plan's required design) rather than folding path discovery into it, so the `tmp_path` positive/negative controls in Task 1 exercise the identical comparison logic the real guard uses.
- Verified the "passes vacuously today" premise directly via `git grep -n "oauth2/authorize" -- . ':!.planning'` before writing any test — matches RESEARCH.md's Pitfall 1 finding that this premise was **fixed** between research time (when `dexter-architecture.md`'s stale URL + leaked token were tracked) and now (that file is confirmed gone from `git ls-files`, per CLAUDE.md's own note that it's "gitignored as of Phase 22").

## Deviations from Plan

**1. [Rule 1 - Bug] Reworded two pre-existing prose comments that collided with the new Python-file marker scan**
- **Found during:** Task 2
- **Issue:** `config.py`'s `INVITE_SCOPES` comment and `logic/__init__.py`'s package docstring (both written during plan 22-01) legitimately explained discord.py's `oauth_url()` helper in prose, which is textually indistinguishable from a real second constructor to a literal-substring scan. Running the freshly-written `test_logic_invite_is_the_only_url_constructor` failed immediately against these two files, not against any actual duplicated URL-building code.
- **Fix:** Reworded both comments to convey the same meaning without repeating the literal substrings `oauth_url(` / `discord.com/oauth2/authorize`.
- **Files modified:** `config.py`, `logic/__init__.py`
- **Commit:** `b477090`

No other deviations — the rest of the plan executed exactly as written, including the exact helper/constant names, docstring conventions, and the `tmp_path`-only positive-control design specified in `<action>`.

## Issues Encountered

None beyond the deviation above.

## User Setup Required

None — no external service configuration required. This is a pure CI/test-infrastructure plan.

## Next Phase Readiness

- `tests/test_invite_drift_guard.py` is committed, green (9/9), and enforces both halves of INVITE-02/SC-3: no public doc can promote a stale/over-privileged invite link (T-22-02), and no future module can hand-build a second invite-URL constructor in Python (T-22-03).
- **Phase-23 hand-off:** Phase 23 must paste the literal output of `build_invite_url()` into the README / `/site` — no shortener, no vanity redirect, no second constructor (D-07). The moment it does, `test_no_doc_contains_a_drifted_invite_url` stops being vacuous and starts enforcing SC-3 with zero further work — no workflow change, no opt-in step.
- Full suite green: 1035 passed, 124 skipped, 0 failed (up from 1026/124 in 22-02 — the 9 new tests). `ruff check .` and `ruff format --check .` both clean on every file touched.
- Phase 22 (invite-plumbing) is now code-complete across all 3 plans: `logic/invite.py::build_invite_url()` (22-01), `/invite` slash command (22-02), and this CI drift guard (22-03). The remaining Phase 22 human-verify items (D-08 Developer Portal byte-for-byte comparison, live "click invite → bot joins" proof, DM usability, granted-permissions confirmation) are parked per the standing acknowledged-deferred pattern (`22-VALIDATION.md`'s Manual-Only rows → `22-HUMAN-UAT.md` at phase close).

---
*Phase: 22-invite-plumbing*
*Completed: 2026-07-14*

## Self-Check: PASSED

`tests/test_invite_drift_guard.py` found on disk; both task commits (`b3fc3a3`, `b477090`) verified present in `git log --oneline --all`.
