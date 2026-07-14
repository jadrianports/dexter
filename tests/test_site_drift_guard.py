"""Built-artifact drift guard for Dexter's invite URL (Phase 23 / PORT-01,
CICD-02 — D-02; threats T-23-DRIFT, T-23-07, T-23-08).

**Why this file exists, distinct from `tests/test_invite_drift_guard.py`:**
choosing Astro as the SSG broke Phase 22's guarantee by construction. The
committed source is now `.astro`/`.ts` — outside the Phase 22 guard's
`.md`/`.html`/`.txt` extension allowlist — and the rendered `dist/index.html`
is never git-tracked, so `git ls-files` (the collection strategy
`tests/test_invite_drift_guard.py` uses) surfaces nothing to scan at all. That
guard would pass **vacuously forever** while the shipped page could carry any
invite URL whatsoever. Widening its extension allowlist to include `.astro`/
`.ts` would not fix this and would actively make it worse: `site/src/config.ts`
assembles `INVITE_URL` from concatenated template literals, so the full
canonical string never appears contiguously in the source — a source-level
regex would match only the leading OAuth2-endpoint-plus-client-id fragment of
that template string and report it as permanent, unfixable "drift" on every
single run.

**The fix is a different collection strategy, not an allowlist change:**
this guard walks the *built* `site/dist/**/*.html` tree with `Path.rglob`
(never `git ls-files` — `dist/` is gitignored by design) and reuses the
Phase 22 guard's exact comparison seam — `_canonical_url()` and
`_collect_offenders()`, imported from `tests.test_invite_drift_guard`, never
re-implemented — so the two guards can never silently drift apart from each
other. The guarantee: the invite URL in the actual bytes shipped to a
browser is byte-identical to `build_invite_url()`'s output, regardless of
which templating layer, string concatenation, or component nesting produced
those bytes.

**`SITE_DIST_REQUIRED` — the skip/fail split that makes this a real CI gate:**
a bare `pytest.skip()` when `site/dist/` is absent behaves identically
whether run locally (correct — a developer with no Node build shouldn't be
blocked) or in CI (catastrophic — it would silently recreate the exact
vacuous-pass hole this file exists to close). Setting `SITE_DIST_REQUIRED=1`
(done only inside `ci.yml`'s site job, plan 23-04) converts the missing-dist
case from a skip into a hard `pytest.fail()`: CI can never quietly skip this
guard because its own build step is what's supposed to produce `dist/` in
the first place.

**Residual limitation, stated honestly (IN-01 discharge):** IN-01 was Phase
22's deferred concern that the original guard's extension allowlist would
miss a URL embedded in a new file type. This artifact-level scan genuinely
discharges IN-01 for this phase's actual shape — and is a *stronger*
guarantee than widening the allowlist would have been, because it inspects
the literal bytes shipped to the browser regardless of what produced them.
But the boundary of that guarantee is real and worth naming: if a future
Astro island or client-side script ever constructed the invite URL at
*runtime in the browser* rather than at build time in static markup, this
scan — which only reads static file bytes — would never see it, because the
URL would never appear as a literal string in `dist/*.html`. That does not
apply today: Astro ships zero client-side JS by default (D-01) and both CTA
anchors are static build-time markup (D-05), so every occurrence of the
invite URL is a literal in the built HTML. The boundary is documented, not
hidden.

Tests:
- test_no_drift_in_built_site                    — THE guard (T-23-DRIFT)
- test_dist_drift_guard_actually_detects_a_mismatch — mandatory positive control (T-23-08)
- test_dist_drift_guard_accepts_the_canonical_url    — negative control for the positive control
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.test_invite_drift_guard import _canonical_url, _collect_offenders, _repo_root

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
    is gitignored by design (site/dist/, added in plan 23-03 Task 1), so a
    git-tracked-file collection strategy would find nothing here regardless
    of what the build actually produced."""
    if not dist_dir.exists():
        return []
    return list(dist_dir.rglob("*.html"))


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def test_no_drift_in_built_site():
    """D-02: guards the actual shipped artifact, not the .astro/.ts source.

    Missing-dist handling is the skip/fail split described in the module
    docstring: `SITE_DIST_REQUIRED=1` (set only by plan 23-04's CI site job)
    turns "no dist/ found" into a hard failure instead of a graceful local
    skip, so CI can never silently recreate the vacuous-pass hole this file
    exists to close.
    """
    files = _dist_html_files(_site_dist_dir())
    if not files:
        if os.getenv("SITE_DIST_REQUIRED"):
            pytest.fail(
                "site/dist/ is empty but SITE_DIST_REQUIRED=1 — "
                "the Astro build step did not run or produced no output"
            )
        pytest.skip("site/dist/ not built (local run, no `npm run build`)")
    offenders = _collect_offenders(files, _canonical_url())
    assert offenders == [], f"drifted invite URL(s) in built site: {offenders}"


def test_dist_drift_guard_actually_detects_a_mismatch(tmp_path):
    """Mandatory positive control (Phase 22 D-10 discipline, mirroring
    `test_drift_guard_actually_detects_a_mismatch`). Proves a green run of
    the guard above is not a false green: a deliberately-wrong URL —
    `permissions=8`, literally Administrator, the exact over-privilege case
    T-23-08 names — run through the real `_collect_offenders` seam must be
    caught, using the same comparison logic the real guard uses."""
    fake_html = tmp_path / "index.html"
    fake_html.write_text(
        '<a href="https://discord.com/oauth2/authorize?client_id=999&permissions=8&scope=bot">Add</a>',
        encoding="utf-8",
    )
    offenders = _collect_offenders([fake_html], _canonical_url())
    assert offenders, "dist/ scanner failed to catch a deliberately-wrong invite URL"


def test_dist_drift_guard_accepts_the_canonical_url(tmp_path):
    """Negative control for the positive control: the real canonical URL,
    embedded verbatim in a built-HTML-shaped fixture, produces ZERO
    offenders. Proves this is a literal-match test, not a blanket "any
    invite URL is an error" test."""
    canonical = _canonical_url()
    fake_html = tmp_path / "index.html"
    fake_html.write_text(f'<a href="{canonical}">add to discord</a>', encoding="utf-8")
    offenders = _collect_offenders([fake_html], canonical)
    assert offenders == []
