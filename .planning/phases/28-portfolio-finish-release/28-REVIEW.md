---
phase: 28-portfolio-finish-release
reviewed: 2026-07-18T00:00:00Z
depth: standard
files_reviewed: 1
files_reviewed_list:
  - tests/test_demo_transcript_guard.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: resolved
resolution: "WR-01 + WR-02 fixed 2026-07-18 (user-selected); IN-01/IN-02/IN-03 accepted (documented latent-only, not fired). Suite 1238 passed / 0 failed after fix."
---

> **Resolution (2026-07-18):** WR-01 (CSS-file-only hex scan → now scans HTML+CSS
> bytes together, `assert css_files` dropped — survives Astro stylesheet inlining)
> and WR-02 (token-leak guard split into `test_no_raw_token_in_built_demo` +
> `test_port05_copy_and_identity_survive_build`) fixed at user request. IN-01/02/03
> accepted as documented latent-only notes. Guard: 5 passed local + CI-shape; full
> suite 1238 passed / 0 failed.


# Phase 28: Code Review Report

**Reviewed:** 2026-07-18
**Depth:** standard
**Files Reviewed:** 1
**Status:** issues_found

## Summary

Reviewed `tests/test_demo_transcript_guard.py`, the Phase 28 drift guard over the
built `site/dist/` demo-transcript token→previewSample contract plus a
build-independent structural guard over `site/src/data/demo-transcript.ts`.

The core token-leak logic is sound and well-controlled. I traced every assertion
against the actual source (`site/src/data/demo-transcript.ts`) and the current
built artifact (`site/dist/`): the split/window structural guard correctly
isolates each token's `previewSample`, the positive control
(`test_dist_scan_detects_a_leaked_token`) genuinely exercises the real
`_raw_tokens_in` detector, the negative control is non-vacuous, and all copy /
hex / previewSample assertions match the current build (verified — the guard is
green today, not a false green). The `SITE_DIST_REQUIRED` skip/fail split
faithfully mirrors the established `test_site_drift_guard.py` convention.

No blockers. The findings below are latent robustness defects (a false-failure
that does not fire on today's build but is coupled to Astro's CSS-inlining
behavior) and scope/quality issues that reduce the guard's clarity and honesty.

## Warnings

### WR-01: CSS-file-only hex scan is a latent false-failure under Astro stylesheet inlining

**File:** `tests/test_demo_transcript_guard.py:174-184`
**Issue:** The after-hours identity check hard-asserts `assert css_files` (line
175) and then searches for the hex values ONLY inside `*.css` files (lines
176-184). Astro's default `build.inlineStylesheets: 'auto'` inlines any
stylesheet below Vite's ~4kB `assetsInlineLimit` directly into an HTML `<style>`
block, in which case `site/dist/` contains **zero** `.css` files and the hex
values live only in the HTML. `site/astro.config.mjs` does not override this
default. Today the built stylesheet is large (confirmed:
`site/dist/_astro/index.*.css` is emitted as a separate file, so the guard is
green), but if the CSS ever shrinks below the inline threshold — or the config
adopts `inlineStylesheets: 'always'` — this test fails on a completely correct
build: `assert css_files` trips first, and even past it `all_css_text` would not
contain the hex. That makes it a brittle, build-topology-dependent guard rather
than an assertion about the shipped identity.
**Fix:** Search for the hex across both HTML and CSS bytes, and drop the hard
`assert css_files`:
```python
all_shipped_text = all_html_text + "\n" + "\n".join(
    f.read_text(encoding="utf-8", errors="ignore") for f in _dist_css_files(dist_dir)
)
assert _IDENTITY_HEX_BG in all_shipped_text, ...
assert _IDENTITY_HEX_ACCENT in all_shipped_text, ...
```

### WR-02: Token-leak guard bundles unrelated PORT-05 design assertions, obscuring failures

**File:** `tests/test_demo_transcript_guard.py:134-184`
**Issue:** `test_no_raw_token_in_built_demo` is named and documented as THE
token-leak guard (D-01.1), but it also asserts proper-case hero/feature copy
(`_PROPER_CASE_SUBSET`, lines 171-172) and after-hours hex identity (lines
177-184). A legitimate copy edit ("Watch it work" → "See it in action") or a
palette tweak now fails a test whose name says "no raw token in built demo," so
the reported failure actively misdirects the reader away from the real cause.
These are also weaker checks than the token scan: they are substring-presence
assertions, so they cannot detect regression of the design, only its total
disappearance. Coupling the token contract to volatile marketing copy/colors
increases maintenance churn on an invariant that has nothing to do with token
resolution.
**Fix:** Split the PORT-05 design confirmation into its own test (e.g.
`test_port05_copy_and_identity_survive_build`) that shares the same
`_dist_html_files` / `_dist_css_files` helpers, leaving
`test_no_raw_token_in_built_demo` focused on the token→previewSample contract
its name and docstring describe.

## Info

### IN-01: Empty-previewSample branch is unreachable; empty value yields a misleading diagnostic

**File:** `tests/test_demo_transcript_guard.py:261-266`
**Issue:** The regex `previewSample:\s*"([^"]+)"` requires `[^"]+` (one or more
non-quote chars), so a genuinely empty `previewSample: ""` never matches. Such an
entry fails at line 262 (`assert match is not None`) with the message "has no
previewSample fallback" — but the entry *does* have a previewSample, it is merely
empty. The intended empty-string guard at line 266
(`assert match.group(1).strip() != ""`) is therefore dead code and can never be
the assertion that fires. The test still correctly fails, but the diagnostic
misattributes the cause.
**Fix:** Widen the capture to include the empty case, e.g.
`re.search(r'previewSample:\s*"([^"]*)"', window)`, so the `.strip() != ""` check
becomes reachable and an empty `""` produces the accurate "previewSample is
empty" message.

### IN-02: Detector regex is uppercase-only, contradicting the "deliberately generic" docstring

**File:** `tests/test_demo_transcript_guard.py:66-69`
**Issue:** The comment claims the pattern is "Deliberately generic ... so a future
differently-named token would still be caught," but `\{\{[A-Z0-9_]+\}\}` only
matches uppercase-alphanumeric-underscore tokens. A camelCase, lowercase, or
whitespaced placeholder (`{{demoLine1}}`, `{{ FOO }}`, `{{foo-bar}}`) would leak
past this guard undetected. The current token convention is uppercase, so this is
not a live gap, but the docstring overstates the coverage.
**Fix:** Either tighten the docstring to state the uppercase-token scope
explicitly, or broaden the class to `\{\{\s*[A-Za-z0-9_-]+\s*\}\}` if genuinely
generic detection is intended.

### IN-03: Hex identity assertions are weak substring-presence checks

**File:** `tests/test_demo_transcript_guard.py:177-184`
**Issue:** `0a0c11` and `ffb454` are asserted as bare substrings of the CSS text.
A six-hex-char sequence can appear coincidentally in minified output unrelated to
the intended `--color-bg` / `--color-accent` values, so the assertion can pass
without the identity actually being applied where intended. This is a
weak-guarantee note, not a failure (verified: both currently appear as the
correct custom-property values).
**Fix:** Optionally anchor to the declaration (e.g. `--color-bg:#0a0c11`) so the
check binds to the semantic role, not just the byte sequence.

---

_Reviewed: 2026-07-18_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
