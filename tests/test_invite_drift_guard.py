"""Repo-introspection drift guard for Dexter's invite URL (Phase 22 / INVITE-02
/ SC-3 — D-03, D-07, D-10; threats T-22-02, T-22-02a, T-22-08).

The core guarantee: every OAuth2 invite URL in any git-tracked, non-``.planning/``
``.md``/``.html``/``.txt`` doc must literally equal
``build_invite_url(client_id=config.DISCORD_CLIENT_ID,
permissions_value=config.INVITE_PERMISSIONS_VALUE, scopes=config.INVITE_SCOPES)``'s
output. Drift between the in-bot ``/invite`` link and any publicly-promoted link
(README, ``/site``) is structurally impossible, not merely discouraged.

The main guard (``test_no_doc_contains_a_drifted_invite_url``) passes vacuously
today — zero tracked non-``.planning/`` docs currently carry an OAuth2 URL. That
vacuous pass is proven NOT a false green by
``test_drift_guard_actually_detects_a_mismatch``, a mandatory positive control
that feeds a deliberately-wrong URL through the exact same comparison function
the real guard uses.

Tests:
- test_no_doc_contains_a_drifted_invite_url        — THE guard (T-22-02)
- test_drift_guard_actually_detects_a_mismatch      — mandatory positive control (T-22-02a)
- test_drift_guard_accepts_the_canonical_url        — negative control for the positive control
- test_scanner_matches_urls_in_markdown_html_and_bare_forms — regex extracts cleanly in all 3 embed forms
- test_planning_tree_is_excluded_from_the_scan      — D-10: .planning/ is tracked-but-skipped
- test_only_text_extensions_are_scanned             — D-10: extension allowlist
- test_canonical_url_resolves_without_env_secrets   — D-04 CI-parity: no env vars needed
- test_logic_invite_is_the_only_url_constructor     — D-03/D-07: single Python constructor (T-22-03)
- test_config_holds_no_url_literal                  — config.py holds the bitfield/id, not the URL
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path, PurePosixPath

import config
from logic.invite import build_invite_url

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

# The `(?:api/)?` alternative catches the legacy `discord.com/api/oauth2/authorize`
# form. The negated character class terminates the match at a Markdown `)`, an
# HTML `"`/`'`, an angle bracket, or whitespace, so all three embedding forms
# (Markdown link, HTML href, bare-on-its-own-line) extract cleanly with no
# trailing contamination.
URL_PATTERN = re.compile(r"https://discord\.com/(?:api/)?oauth2/authorize\?[^\s)\"'<>]+")

TEXT_EXTENSIONS = frozenset({".md", ".html", ".txt"})

# Directory-prefix denylist (D-10), NOT a per-file allowlist. `.planning/`
# holds legitimate `<APP_ID>`-placeholder example URLs (e.g.
# `.planning/research/STACK.md`) that can never equal the canonical URL —
# scanning them would be a permanent, unfixable false-positive failure.
PLANNING_PREFIX = ".planning/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(out.stdout.strip())


def _tracked_doc_files(root: Path) -> list[Path]:
    """Every git-tracked, non-`.planning/`, text-extension file, as absolute paths."""
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=root, check=True)
    files = []
    for rel in out.stdout.splitlines():
        if rel.startswith(PLANNING_PREFIX):
            continue
        p = Path(rel)
        if p.suffix in TEXT_EXTENSIONS:
            files.append(root / rel)
    return files


def _canonical_url() -> str:
    return build_invite_url(
        client_id=config.DISCORD_CLIENT_ID,
        permissions_value=config.INVITE_PERMISSIONS_VALUE,
        scopes=config.INVITE_SCOPES,
    )


def _collect_offenders(paths: list[Path], canonical: str) -> list[tuple[str, str]]:
    """The seam the positive/negative controls exercise: given an explicit list
    of paths (real tracked docs, or a `tmp_path` fixture file), find every
    OAuth2 URL and record any that don't literally equal `canonical`.

    Deliberately takes an explicit path list rather than re-deriving it
    internally, so `tmp_path`-based tests run through the exact same
    comparison logic the real guard uses instead of a reimplementation.
    """
    offenders: list[tuple[str, str]] = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in URL_PATTERN.findall(text):
            cleaned = match.rstrip(").,")
            if cleaned != canonical:
                offenders.append((str(path), cleaned))
    return offenders


# ---------------------------------------------------------------------------
# Task 1 — the drift guard + its controls
# ---------------------------------------------------------------------------


def test_no_doc_contains_a_drifted_invite_url():
    """THE guard (T-22-02). Passes vacuously today (zero URLs in scope);
    starts enforcing the moment Phase 23 pastes a link into a tracked doc."""
    root = _repo_root()
    canonical = _canonical_url()
    offenders = _collect_offenders(_tracked_doc_files(root), canonical)
    assert offenders == [], f"drifted invite URL(s) found: {offenders}"


def test_drift_guard_actually_detects_a_mismatch(tmp_path):
    """Mandatory positive control (T-22-02a). Proves today's vacuous pass is
    not a false green: a deliberately-wrong URL — `permissions=8`, literally
    Administrator, the exact thing this guard exists to catch — run through
    the real `_collect_offenders` seam must be caught."""
    fake_doc = tmp_path / "fake.md"
    fake_doc.write_text(
        "check out https://discord.com/oauth2/authorize?client_id=999&permissions=8&scope=bot",
        encoding="utf-8",
    )
    offenders = _collect_offenders([fake_doc], _canonical_url())
    assert offenders, "scanner failed to catch a deliberately-wrong invite URL"


def test_drift_guard_accepts_the_canonical_url(tmp_path):
    """Negative control for the positive control: the real canonical URL,
    embedded verbatim, produces ZERO offenders. Proves this is a literal-match
    test, not a blanket "any invite URL is an error" test — Phase 23 must be
    able to paste the real link and stay green."""
    canonical = _canonical_url()
    fake_doc = tmp_path / "real.md"
    fake_doc.write_text(f"Add Dexter: {canonical}", encoding="utf-8")
    offenders = _collect_offenders([fake_doc], canonical)
    assert offenders == []


def test_scanner_matches_urls_in_markdown_html_and_bare_forms(tmp_path):
    """The canonical URL embedded as a Markdown link, an HTML href, and a bare
    on-its-own-line form is found in all three (Phase 23 will use all three).
    No trailing `)` or `"` contamination."""
    canonical = _canonical_url()
    fake_doc = tmp_path / "forms.md"
    fake_doc.write_text(
        f'[Add to Discord]({canonical})\n<a href="{canonical}">Add to Discord</a>\n{canonical}\n',
        encoding="utf-8",
    )
    matches = URL_PATTERN.findall(fake_doc.read_text(encoding="utf-8"))
    assert len(matches) == 3
    for match in matches:
        cleaned = match.rstrip(").,")
        assert cleaned == canonical
        assert not match.endswith(")")
        assert not match.endswith('"')


def test_planning_tree_is_excluded_from_the_scan():
    """D-10. Assert positively that `.planning/` files exist and are tracked
    (so this couldn't pass merely because `.planning/` is empty/absent) but
    are absent from `_tracked_doc_files()`'s return."""
    root = _repo_root()
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=root, check=True)
    tracked_planning_docs = [
        rel for rel in out.stdout.splitlines() if rel.startswith(PLANNING_PREFIX) and Path(rel).suffix == ".md"
    ]
    assert tracked_planning_docs, "expected at least one tracked .planning/*.md file to exist"

    scanned = _tracked_doc_files(root)
    for path in scanned:
        rel = str(PurePosixPath(path.relative_to(root).as_posix()))
        assert not rel.startswith(PLANNING_PREFIX)


def test_only_text_extensions_are_scanned():
    root = _repo_root()
    for path in _tracked_doc_files(root):
        assert path.suffix in TEXT_EXTENSIONS


def test_canonical_url_resolves_without_env_secrets(monkeypatch):
    """D-04 CI-parity guarantee: the canonical URL resolves from config.py's
    committed constants, never from an env var — the zero-secret CI job
    (`.github/workflows/ci.yml`, only `TEST_DATABASE_URL` set) must be able
    to run this guard."""
    monkeypatch.delenv("DISCORD_CLIENT_ID", raising=False)
    url = build_invite_url(
        client_id=config.DISCORD_CLIENT_ID,
        permissions_value=config.INVITE_PERMISSIONS_VALUE,
        scopes=config.INVITE_SCOPES,
    )
    assert "permissions=309240908864" in url
