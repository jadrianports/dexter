"""Repo-introspection drift guard for Dexter's hosting-honesty scrub (Phase 24
/ HOST-01 — D-12; threats T-24-07, T-24-08).

The core guarantee: no git-tracked, non-sealed-archive file may contain a dead
``Koyeb``/``Oracle`` reference (both hosting substrates this repo abandoned —
see CLAUDE.md's Tech Stack "Hosting" bullet). ``Render`` is NOT zero-tolerance
— it is both a legitimate English word ("render a progress bar", "re-render
the embed") and a hosting-provider name, so it is enforced via an explicit,
hardcoded allowlist diff instead: any un-allowlisted hit fails the build,
which is exactly how a *new* Render-provider reference would be caught.

Three prefixes are sealed and excluded from both scans (D-03/D-10):
``.planning/``, ``milestones/``, ``docs/superpowers/`` — all archival/scratch
content that legitimately discusses the abandoned Koyeb/Oracle hosting
history and can never be scrubbed without destroying that history. This
guard's OWN file path is also excluded from both scans, since it necessarily
contains the literal strings "Koyeb", "Oracle", and "render" in its own
regex/allowlist/positive-control fixtures.

Tests:
- test_no_koyeb_or_oracle_references          — Part 1, zero-tolerance (HOST-01)
- test_render_hits_are_all_allowlisted        — Part 2, allowlist diff (HOST-01)
- test_drift_guard_actually_detects_koyeb      — mandatory positive control (T-24-07)
- test_drift_guard_accepts_a_clean_file        — negative control for the positive control
- test_sealed_archives_are_excluded            — D-03/D-10 guard-of-the-guard (T-24-08)
- test_koyeb_doc_removed_and_docker_doc_present — HOST-02 file-swap backstop
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path, PurePosixPath

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

# Sealed archival prefixes (D-03/D-10): legitimate historical/scratch content
# that discusses the abandoned Koyeb/Oracle hosting substrates and can never
# be scrubbed. A directory-prefix denylist, NOT a per-file allowlist.
EXCLUDED_PREFIXES = (".planning/", "milestones/", "docs/superpowers/")

# This guard's own file necessarily contains the literal strings "Koyeb",
# "Oracle", and "render" (in its docstring, regex source, and fixtures) —
# it MUST exclude itself from both scans or it trips on its own content.
# Scoped to just this one file path (not all of `tests/`) so any OTHER test
# file that reintroduces a dead hosting reference stays caught.
_SELF_PATH = "tests/test_hosting_drift_guard.py"

KOYEB_ORACLE_PATTERN = re.compile(r"\b(Koyeb|Oracle)\b", re.IGNORECASE)
RENDER_PATTERN = re.compile(r"\brender[a-z]*\b", re.IGNORECASE)

# A small, hardcoded, reviewable literal set of (file, line) pairs where
# "render"/"rendering"/"rendered"/"renders" is the legitimate English word,
# not a hosting-provider reference — the same "reviewability of the literal
# list IS the control" discipline as the Phase 21 T-21-03 / Phase 22
# `_CONSTRUCTOR_MARKERS` precedent. Derived from the real post-scrub repo
# state via `git grep -niE '\brender[a-z]*\b'` (excluding sealed prefixes),
# NOT copied blindly from RESEARCH.md's pre-scrub line numbers.
RENDER_ALLOWLIST = frozenset(
    {
        ("CLAUDE.md", 85),
        ("README.md", 21),
        ("README.md", 23),
        ("README.md", 27),
        ("bot.py", 696),
        ("cogs/admin.py", 90),
        ("cogs/ai.py", 327),
        ("cogs/memory.py", 63),
        ("cogs/memory.py", 69),
        ("cogs/music.py", 311),
        ("cogs/music.py", 322),
        ("cogs/ops.py", 39),
        ("cogs/ops.py", 163),
        ("cogs/ops.py", 415),
        ("personality/prompts.py", 144),
        ("personality/prompts.py", 194),
        ("personality/prompts.py", 199),
        ("personality/prompts.py", 202),
        ("personality/prompts.py", 211),
        ("scripts/render_demo_gif.py", 2),
        ("scripts/render_demo_gif.py", 52),
        ("site/src/components/DemoMock.astro", 7),
        ("site/src/data/demo-transcript.ts", 11),
        ("site/src/styles/global.css", 133),
        ("tests/test_formatters.py", 1),
        ("tests/test_prompts.py", 113),
        ("tests/test_prompts.py", 120),
        ("tests/test_prompts.py", 249),
        ("tests/test_site_drift_guard.py", 7),
        ("utils/embeds.py", 209),
        ("utils/embeds.py", 293),
        ("utils/formatters.py", 1),
        ("utils/formatters.py", 62),
    }
)


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


def _tracked_non_archive_files(root: Path) -> list[Path]:
    """Every git-tracked file NOT under a sealed-archive prefix (D-03, D-10)
    and not this guard's own file. Deliberately scans ALL tracked files (no
    extension filter) — a Koyeb/Oracle/Render reference can live in `.py`,
    `.yml`, or `.md` alike."""
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=root, check=True)
    files = []
    for rel in out.stdout.splitlines():
        if rel.startswith(EXCLUDED_PREFIXES) or rel == _SELF_PATH:
            continue
        files.append(root / rel)
    return files


def _scan_for_zero_tolerance_terms(paths: list[Path]) -> list[tuple[str, str]]:
    """The seam the positive/negative controls exercise: given an explicit
    list of paths (real tracked files, or a `tmp_path` fixture file), find
    every Koyeb/Oracle hit."""
    offenders: list[tuple[str, str]] = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in KOYEB_ORACLE_PATTERN.finditer(text):
            offenders.append((str(path), m.group(0)))
    return offenders


# ---------------------------------------------------------------------------
# Task 1 — the drift guard + its controls
# ---------------------------------------------------------------------------


def test_no_koyeb_or_oracle_references():
    """Part 1: THE zero-tolerance guard (HOST-01). Passes on the post-scrub
    repo (plans 24-01/24-02 removed every live Koyeb/Oracle reference) and
    fails CI the moment a future phase pastes old hosting prose back in."""
    root = _repo_root()
    offenders = _scan_for_zero_tolerance_terms(_tracked_non_archive_files(root))
    assert offenders == [], f"dead hosting-target reference(s) found: {offenders}"


def test_render_hits_are_all_allowlisted():
    """Part 2: Render is enforced as an allowlist diff, not zero-tolerance,
    because it is also a legitimate English word ("render a progress bar").
    Any `render`/`rendering`/`rendered`/`renders` hit NOT in the hardcoded
    `RENDER_ALLOWLIST` is a build-failing offender — this is exactly how a
    real Render-provider reintroduction would be caught."""
    root = _repo_root()
    offenders: list[str] = []
    for path in _tracked_non_archive_files(root):
        rel = str(PurePosixPath(path.relative_to(root).as_posix()))
        text = path.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), start=1):
            if RENDER_PATTERN.search(line) and (rel, i) not in RENDER_ALLOWLIST:
                offenders.append(f"{rel}:{i}: {line.strip()}")
    assert offenders == [], f"un-allowlisted Render reference(s): {offenders}"


def test_drift_guard_actually_detects_koyeb(tmp_path):
    """Mandatory positive control (T-24-07). Proves the zero-tolerance scan
    is not a vacuous pass: a deliberately-reintroduced Koyeb reference, run
    through the real `_scan_for_zero_tolerance_terms` seam, must be caught."""
    fake = tmp_path / "fake.py"
    fake.write_text("# deployed to Koyeb\n", encoding="utf-8")
    offenders = _scan_for_zero_tolerance_terms([fake])
    assert offenders, "scanner failed to catch a deliberately-reintroduced Koyeb reference"


def test_drift_guard_also_detects_oracle(tmp_path):
    """Positive control, Oracle variant — both zero-tolerance terms must be
    independently catchable, not just Koyeb."""
    fake = tmp_path / "fake.py"
    fake.write_text("# runs on Oracle Cloud A1\n", encoding="utf-8")
    offenders = _scan_for_zero_tolerance_terms([fake])
    assert offenders, "scanner failed to catch a deliberately-reintroduced Oracle reference"


def test_drift_guard_accepts_a_clean_file(tmp_path):
    """Negative control for the positive control: a clean file with no
    hosting terms produces zero offenders — proves this is a targeted-term
    test, not a blanket "any word starting with K or O" false-positive trap."""
    fake = tmp_path / "clean.py"
    fake.write_text("# runs in Docker Compose against Neon\n", encoding="utf-8")
    offenders = _scan_for_zero_tolerance_terms([fake])
    assert offenders == []


def test_sealed_archives_are_excluded():
    """D-03/D-10 guard-of-the-guard (T-24-08). Assert positively that at
    least one tracked file exists under each sealed prefix that actually has
    tracked content today (`.planning/`, `docs/superpowers/` — so exclusion
    isn't vacuously true because the prefix is empty/absent) but is ABSENT
    from `_tracked_non_archive_files()`'s return.

    Note: `milestones/` is also in `EXCLUDED_PREFIXES` per D-03/D-10, but in
    the current repo layout milestone docs live nested under
    `.planning/milestones/` (already covered by the `.planning/` prefix), so
    no tracked file starts with the bare top-level `milestones/` prefix
    today. It's kept in the tuple defensively (verified present below) in
    case milestone docs are ever promoted out of `.planning/`."""
    root = _repo_root()
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=root, check=True)
    all_tracked = out.stdout.splitlines()

    prefixes_with_tracked_content = (".planning/", "docs/superpowers/")
    for prefix in prefixes_with_tracked_content:
        tracked_under_prefix = [rel for rel in all_tracked if rel.startswith(prefix)]
        assert tracked_under_prefix, f"expected at least one tracked file under {prefix!r} to exist"

    assert "milestones/" in EXCLUDED_PREFIXES, "expected the defensive 'milestones/' prefix to be encoded"

    scanned = _tracked_non_archive_files(root)
    scanned_rels = {str(PurePosixPath(p.relative_to(root).as_posix())) for p in scanned}
    for prefix in EXCLUDED_PREFIXES:
        for rel in all_tracked:
            if rel.startswith(prefix):
                assert rel not in scanned_rels, f"sealed file {rel!r} leaked into the scan"

    # The guard's own file must exist on disk (it obviously does — this is
    # that file) and must be excluded from the scan. Checked via filesystem
    # existence rather than `git ls-files` membership, since this assertion
    # must hold even before this file's own introducing commit lands.
    assert (root / _SELF_PATH).exists(), "expected the guard's own file to exist on disk"
    assert _SELF_PATH not in scanned_rels, "guard failed to exclude its own file from the scan"


def test_koyeb_doc_removed_and_docker_doc_present():
    """HOST-02 file-swap backstop: the dead Koyeb runbook is gone and its
    Docker+Neon replacement (plan 24-02) exists."""
    root = _repo_root()
    assert not (root / "docs" / "DEPLOY-KOYEB.md").exists()
    assert (root / "docs" / "DEPLOY-DOCKER.md").exists()
