"""Built-artifact + source drift guard for Dexter's demo-transcript
token->previewSample contract (Phase 28 / PORT-05 confirmation — D-01.1,
D-01.2; threat T-28-01).

**Why this file exists, distinct from `tests/test_site_drift_guard.py`:**
that file guards a completely different invariant (the invite-URL byte-check
over `site/dist/`). This repo's established convention is one topic per
drift-guard file (`test_invite_drift_guard.py`, `test_site_drift_guard.py`,
`test_hosting_drift_guard.py` are all single-purpose) — extending an
unrelated file would make its own docstring misleading. This guard exists to
lock down `site/src/data/demo-transcript.ts`'s `resolveLine()` contract: the
`{{DEXTER_DEMO_LINE_*}}` placeholder tokens are legitimate, intentional
scaffolding in the *source* (PORT-02 is still blocked-on-human — see
`site/src/data/demo-transcript.ts`'s own module docstring), but they must
NEVER survive into the *shipped* `site/dist/` bytes a browser actually
receives. `resolveLine()` is supposed to substitute each unfilled token for
its `previewSample` fallback at Astro build time; this guard proves that
substitution actually happened, and proves the substitution behavior can't
silently regress even before a build exists.

**Collection strategy — `Path.rglob` over the built tree, never
`git ls-files`:** `site/dist/` is gitignored by design (see
`test_site_drift_guard.py`'s own docstring for the same reasoning), so a
git-tracked-file collection strategy would find nothing here regardless of
what the build actually produced.

**`SITE_DIST_REQUIRED` — the skip/fail split that makes this a real CI
gate:** reuses the exact env var name `test_site_drift_guard.py` already
established (do not invent a second one). A bare `pytest.skip()` when
`site/dist/` is absent behaves identically whether run locally (correct — a
developer with no Node build shouldn't be blocked) or in CI (catastrophic —
it would silently recreate a vacuous-pass hole). Setting `SITE_DIST_REQUIRED=1`
(done only inside `ci.yml`'s `site` job) converts the missing-dist case from
a skip into a hard `pytest.fail()`.

**Pitfall 1 (28-RESEARCH.md), directly confirmed this session:** the literal
English phrase "after hours" is NOT present anywhere in the built artifact —
it lives only in a `global.css` comment that the Astro/Vite minifier strips.
Asserting that literal string against `dist/` would be a guaranteed,
permanent false failure on a correct build. The after-hours visual identity
is instead asserted via the surviving hex color values (`0a0c11` near-black
background, `ffb454` amber accent) that ARE present in the built CSS.

Tests:
- test_no_raw_token_in_built_demo              — THE dist-scan guard (D-01.1, T-28-01)
- test_dist_scan_detects_a_leaked_token         — mandatory positive control
- test_dist_scan_accepts_resolved_preview_samples — negative control for the positive control
- test_every_unfilled_token_entry_has_a_preview_sample — build-independent structural guard (D-01.2)
"""

from __future__ import annotations

import html
import os
import re
from pathlib import Path

import pytest

from tests.test_invite_drift_guard import _repo_root

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

# Any `{{SOME_TOKEN}}`-shaped placeholder. Deliberately generic (not scoped to
# just DEXTER_DEMO_LINE_*) so a future differently-named token would still be
# caught by the same detector.
_RAW_TOKEN_PATTERN = re.compile(r"\{\{[A-Z0-9_]+\}\}")

# Verified present in a fresh `npm run build` this session (28-RESEARCH.md
# Code Examples) — proves resolveLine() resolved the fallback at build time,
# not just that no raw token leaked.
_PREVIEW_SAMPLE_1 = "Seventeen songs and four of them are the same sad boy. Bold curatorial vision."
_PREVIEW_SAMPLE_2 = "Third time today. I'm keeping notes. For later."

# A representative subset of the proper-case hero/feature copy (28-RESEARCH.md
# Code Examples) — confirms the broader PORT-05 redesign (not just the demo
# transcript) survives into the shipped artifact.
_PROPER_CASE_SUBSET = (
    "An AI with opinions",
    "What it actually does",
    "Watch it work",
    "Known limits",
)

# After-hours identity: the surviving hex values, NEVER the literal phrase
# "after hours" (Pitfall 1 — that phrase lives only in a stripped CSS comment).
_IDENTITY_HEX_BG = "0a0c11"
_IDENTITY_HEX_ACCENT = "ffb454"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _site_dist_dir() -> Path:
    """Derived from `_repo_root()`, not a bare relative `Path("site/dist")` —
    CI runs pytest from the repo root, but a local invocation may not, and
    this must be cwd-independent either way."""
    return _repo_root() / "site" / "dist"


def _dist_html_files(dist_dir: Path) -> list[Path]:
    """Filesystem walk over the BUILT tree — never `git ls-files`. `dist/`
    is gitignored by design, so a git-tracked-file collection strategy would
    find nothing here regardless of what the build actually produced."""
    if not dist_dir.exists():
        return []
    return list(dist_dir.rglob("*.html"))


def _dist_css_files(dist_dir: Path) -> list[Path]:
    """Same rglob strategy, `*.css` — needed for the after-hours identity
    hex assertions, which live in the built CSS, not the HTML."""
    if not dist_dir.exists():
        return []
    return list(dist_dir.rglob("*.css"))


def _raw_tokens_in(text: str) -> list[str]:
    """Pure detector: every `{{...}}`-shaped raw token found in `text`. The
    positive/negative controls feed this exact function synthetic strings so
    the controls exercise the real detection logic, never a reimplementation."""
    return _RAW_TOKEN_PATTERN.findall(text)


# ---------------------------------------------------------------------------
# The dist-scan guard (D-01.1)
# ---------------------------------------------------------------------------


def test_no_raw_token_in_built_demo():
    """D-01.1: no raw `{{...}}` placeholder ships in the built site, and the
    resolved `previewSample` fallbacks + proper-case copy + after-hours
    identity hex all survive into the shipped bytes.

    Missing-dist handling mirrors `test_site_drift_guard.py`'s skip/fail
    split exactly: `SITE_DIST_REQUIRED=1` (set only by `ci.yml`'s `site`
    job) turns "no dist/ found" into a hard failure instead of a graceful
    local skip, so CI can never silently recreate a vacuous-pass hole.
    """
    dist_dir = _site_dist_dir()
    html_files = _dist_html_files(dist_dir)
    if not html_files:
        if os.getenv("SITE_DIST_REQUIRED"):
            pytest.fail(
                "site/dist/ is empty but SITE_DIST_REQUIRED=1 — the Astro build step did not run or produced no output"
            )
        pytest.skip("site/dist/ not built (local run, no `npm run build`)")

    for html_file in html_files:
        text = html_file.read_text(encoding="utf-8", errors="ignore")
        tokens = _raw_tokens_in(text)
        assert tokens == [], f"raw placeholder token(s) leaked into {html_file}: {tokens}"

    # HTML-unescaped: Astro/JSX-style templating escapes apostrophes (e.g. "I'm"
    # -> "I&#39;m"), so the literal previewSample string only matches after
    # decoding HTML entities back to plain text.
    all_html_text = html.unescape("\n".join(f.read_text(encoding="utf-8", errors="ignore") for f in html_files))
    assert _PREVIEW_SAMPLE_1 in all_html_text, (
        f"previewSample fallback 1 not found in shipped HTML — resolveLine() may not have "
        f"resolved the {{DEXTER_DEMO_LINE_1}} token: {_PREVIEW_SAMPLE_1!r}"
    )
    assert _PREVIEW_SAMPLE_2 in all_html_text, (
        f"previewSample fallback 2 not found in shipped HTML — resolveLine() may not have "
        f"resolved the {{DEXTER_DEMO_LINE_2}} token: {_PREVIEW_SAMPLE_2!r}"
    )

    for copy in _PROPER_CASE_SUBSET:
        assert copy in all_html_text, f"proper-case copy {copy!r} missing from shipped HTML"

    css_files = _dist_css_files(dist_dir)
    assert css_files, "no built CSS files found under site/dist/ — cannot verify after-hours identity"
    all_css_text = "\n".join(f.read_text(encoding="utf-8", errors="ignore") for f in css_files)
    assert _IDENTITY_HEX_BG in all_css_text, (
        f"after-hours near-black background hex {_IDENTITY_HEX_BG!r} missing from built CSS "
        "(NOTE: never assert the literal phrase 'after hours' — it lives only in a stripped CSS comment)"
    )
    assert _IDENTITY_HEX_ACCENT in all_css_text, (
        f"after-hours amber accent hex {_IDENTITY_HEX_ACCENT!r} missing from built CSS "
        "(NOTE: never assert the literal phrase 'after hours' — it lives only in a stripped CSS comment)"
    )


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


def test_dist_scan_detects_a_leaked_token():
    """Mandatory positive control (D-01 discipline, mirroring
    `test_dist_drift_guard_actually_detects_a_mismatch`). Proves a green run
    of the guard above is not a false green: a literal, unresolved
    `{{DEXTER_DEMO_LINE_1}}` token run through the real `_raw_tokens_in`
    detector must be caught."""
    fake_html_text = '<p class="dexter-line">{{DEXTER_DEMO_LINE_1}}</p>'
    tokens = _raw_tokens_in(fake_html_text)
    assert tokens, "detector failed to catch a deliberately-leaked raw placeholder token"
    assert "{{DEXTER_DEMO_LINE_1}}" in tokens


def test_dist_scan_accepts_resolved_preview_samples():
    """Negative control for the positive control: real, resolved
    `previewSample` text — the shape `resolveLine()` actually produces — must
    NOT trip the detector. Proves this is a raw-token-shaped-string test, not
    a blanket "any curly brace is an error" test."""
    fake_html_text = f'<p class="dexter-line">{_PREVIEW_SAMPLE_1}</p><p class="dexter-line">{_PREVIEW_SAMPLE_2}</p>'
    tokens = _raw_tokens_in(fake_html_text)
    assert tokens == [], f"detector false-positived on legitimate resolved previewSample text: {tokens}"


# ---------------------------------------------------------------------------
# Build-independent structural guard (D-01.2)
# ---------------------------------------------------------------------------


def test_every_unfilled_token_entry_has_a_preview_sample():
    """D-01.2: the source-level pairing invariant, checked without requiring
    a build. `site/src/data/demo-transcript.ts` currently has exactly two
    dexter-speaker entries, each carrying an unfilled `{{DEXTER_DEMO_LINE_*}}`
    token — a hardcoded-pair assertion over those two known entries is
    proportionate (28-RESEARCH.md Open Question 2 recommendation).

    This guard asserts the pairing invariant ONLY — it must NOT assert token
    absence in the source. Tokens legitimately live in the source until a
    human replaces them with verbatim Dexter output (PORT-02, D-06); that is
    the contract this test protects, not something it flags as a defect.
    """
    src_path = _repo_root() / "site" / "src" / "data" / "demo-transcript.ts"
    src_text = src_path.read_text(encoding="utf-8")

    assert "{{DEXTER_DEMO_LINE_1}}" in src_text, (
        "expected token {{DEXTER_DEMO_LINE_1}} not found in demo-transcript.ts — "
        "if PORT-02 has landed and replaced it with a real line, this hardcoded-pair "
        "assertion needs updating, not silently removed"
    )
    assert "{{DEXTER_DEMO_LINE_2}}" in src_text, (
        "expected token {{DEXTER_DEMO_LINE_2}} not found in demo-transcript.ts — "
        "if PORT-02 has landed and replaced it with a real line, this hardcoded-pair "
        "assertion needs updating, not silently removed"
    )

    # Pair each known unfilled token with its previewSample: the previewSample
    # key must appear between this token's line and the next `text:` key (or
    # end of file), never absent, never emptied to "".
    entries = re.split(r'text:\s*"\{\{DEXTER_DEMO_LINE_\d+\}\}"', src_text)
    # entries[0] is everything before the first token; entries[1:] are the
    # text following each token occurrence, up to the next split point.
    assert len(entries) == 3, (
        f"expected exactly 2 unfilled {{DEXTER_DEMO_LINE_*}} token entries in demo-transcript.ts, "
        f"found {len(entries) - 1} — a new entry was added without updating this structural guard"
    )
    for i, following_text in enumerate(entries[1:], start=1):
        # Only look at the text up to the next `text:` key (the start of the
        # next transcript entry), so we don't accidentally match a
        # previewSample belonging to a later entry.
        next_text_key = following_text.find("text:")
        window = following_text if next_text_key == -1 else following_text[:next_text_key]
        match = re.search(r'previewSample:\s*"([^"]+)"', window)
        assert match is not None, (
            f"unfilled token entry #{i} in demo-transcript.ts has no previewSample fallback — "
            "a raw {{...}} token would ship to production if this entry were built right now"
        )
        assert match.group(1).strip() != "", f"unfilled token entry #{i}'s previewSample is empty"
