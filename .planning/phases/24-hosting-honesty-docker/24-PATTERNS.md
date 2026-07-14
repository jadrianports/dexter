# Phase 24: Hosting Honesty & Docker - Pattern Map

**Mapped:** 2026-07-15
**Files analyzed:** 16 (2 new, 10 scrub-target edits, 4 deletions)
**Analogs found:** 16 / 16 (2 exact, 10 role-match/tag-preservation, 4 no-analog-needed deletions)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `tests/test_hosting_drift_guard.py` (NEW, D-12) | test (repo-introspection drift guard) | batch/transform (scan tracked files → assert) | `tests/test_invite_drift_guard.py` (primary) + `tests/test_site_drift_guard.py` (secondary, for the "why a second guard" doc-comment convention) | exact |
| `docs/DEPLOY-DOCKER.md` (NEW, D-05/D-06) | config/docs | request-response (human-run runbook) | `docs/DEPLOY-KOYEB.md` (being `git rm`'d — read for structure before deletion) | exact |
| `24-HOST-UAT.md` (NEW, D-08) | docs | request-response (human checklist) | prior `*-HUMAN-UAT.md` files, e.g. `16-HUMAN-UAT.md`/`17-HUMAN-UAT.md` (pattern only — not read this session; convention is well-established, see RESEARCH.md §HOST-03 UAT Shape) | role-match |
| `config.py:22` | config | transform (prose-only) | n/a — single-line comment edit, D-04 tag-preservation | exact (worked example given) |
| `bot.py` (~216–264, 578–589) | config/service (health endpoint comments) | request-response (`/health` aiohttp route, unchanged behavior) | n/a — comment-only edit around live code | exact |
| `Dockerfile` (lines 1–2) | config | build | n/a — header comment edit | exact |
| `docker-compose.yml` (Oracle-era legacy comment) | config | build | n/a — comment-only edit | exact |
| `.env.example` | config | transform (template reframe) | n/a — full-file reframe per D-07 | exact |
| `CLAUDE.md` (Hosting bullet, Phase-5 log, Docker/Koyeb log-viewer note) | docs | transform | n/a — prose rewrite in an already-read file | exact |
| `tests/test_config.py` | test | transform (comment/docstring only, no assertion change) | n/a — tag preserved, zero test-behavior change | exact |
| `utils/logger.py:41` | utility | transform (comment) | n/a — single-line comment, keep `(K-16)` | exact |
| `scripts/memory_spike.py` | utility | transform (comment) | n/a — single-line comment, keep `(K-04)` | exact |
| `utils/embeds.py:294` | utility | transform (comment) | n/a — single-line comment, keep `(D-19)` (D-11) | exact |
| `scripts/archive/{backup,deploy,keepalive}.sh`, `lifecycle-policy.json` (D-02) | utility (deleted) | file-I/O (dead ops scripts) | n/a — `git rm`, no analog needed | n/a |
| `scripts/seed_restore_test.py` (D-11, delete) | utility (deleted) | file-I/O (dead restore-proof script) | n/a — `git rm`, no analog needed | n/a |

## Pattern Assignments

### `tests/test_hosting_drift_guard.py` (test, batch/transform) — THE HIGH-VALUE MAPPING

**Primary analog:** `tests/test_invite_drift_guard.py` (full file read above — 265 lines)
**Secondary analog (for the module-docstring "why this file, why not reuse X" convention):** `tests/test_site_drift_guard.py`

This new guard is structurally simpler than the invite guard (no URL-construction seam to
import, no `logic/` single-constructor invariant to prove) — it needs only the **collection
helper + two-part scan + positive/negative controls** shape. Copy the following pieces
directly, adapting terms:

**1. Module docstring convention** (`tests/test_invite_drift_guard.py:1-28`) — state the
guarantee, name the Task/threat IDs (`D-12`), list every test function up front with a
one-line purpose tag. Mirror this exactly; swap invite-URL language for hosting-term language,
and cite `HOST-01` / `D-12` instead of `INVITE-02`/`T-22-*`.

**2. `_repo_root()` helper** (lines 64-71) — copy verbatim, no changes needed:
```python
def _repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(out.stdout.strip())
```

**3. `_tracked_non_archive_files()` helper** — adapt `_tracked_doc_files()` (lines 74-84).
Key differences from the invite guard's version: (a) this new guard scans **all tracked
files**, not just `.md`/`.html`/`.txt` (a "Koyeb" reference could live in `.py`, `.yml`, or
`.md`) — so drop the `TEXT_EXTENSIONS` filter entirely; (b) the exclusion prefix list must
include THREE prefixes per D-03/D-10, not one:
```python
# Adapted from tests/test_invite_drift_guard.py:56, 74-84 (PLANNING_PREFIX pattern)
EXCLUDED_PREFIXES = (".planning/", "milestones/", "docs/superpowers/")

def _tracked_non_archive_files(root: Path) -> list[Path]:
    """Every git-tracked file NOT under a sealed-archive prefix (D-03, D-10)."""
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=root, check=True)
    files = []
    for rel in out.stdout.splitlines():
        if rel.startswith(EXCLUDED_PREFIXES):
            continue
        files.append(root / rel)
    return files
```
Note: `scripts/archive/*` will already be gone (D-02's `git rm` runs in the same phase) so it
needs no explicit exclusion — `git ls-files` simply won't list it post-deletion. Order the
drift-guard task AFTER the deletion task within the wave, or the pre-deletion `git ls-files`
snapshot would still include those paths on a stale checkout — but since this is a fresh
`subprocess.run` per test invocation, not a cached list, this is a non-issue as long as the
deletion is committed before the guard test runs in CI.

**4. Two-part scan-and-assert body** — mirrors `test_no_doc_contains_a_drifted_invite_url`
(lines 119-125) but implements RESEARCH.md's Part-1/Part-2 logic instead of a URL-equality
diff:
```python
# Part 1 pattern — zero-tolerance terms (adapt from the offender-collection shape,
# lines 95-111 `_collect_offenders`, but simpler: substring/word-boundary match, not URL parse)
KOYEB_ORACLE_PATTERN = re.compile(r"\b(Koyeb|Oracle)\b", re.IGNORECASE)

def _scan_for_zero_tolerance_terms(paths: list[Path]) -> list[tuple[str, str]]:
    offenders = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in KOYEB_ORACLE_PATTERN.finditer(text):
            offenders.append((str(path), m.group(0)))
    return offenders

def test_no_koyeb_or_oracle_references():
    root = _repo_root()
    offenders = _scan_for_zero_tolerance_terms(_tracked_non_archive_files(root))
    assert offenders == [], f"dead hosting-target reference(s) found: {offenders}"
```
```python
# Part 2 pattern — Render allowlist diff (RESEARCH.md § Verification Grep Command,
# the ~23-line allowlist table). Hardcode the allowlist as a literal frozenset of
# (file, line) pairs, same "reviewability of the literal list IS the control"
# discipline as tests/test_invite_drift_guard.py's _CONSTRUCTOR_MARKERS (line 222 comment).
RENDER_ALLOWLIST = frozenset({
    ("cogs/admin.py", 90), ("cogs/music.py", 304), ("cogs/music.py", 1688),
    ("cogs/ops.py", 39), ("cogs/ops.py", 415),
    ("docs/superpowers/plans/2026-04-12-dexter-phase1-mvp.md", 335),  # excluded anyway by D-10 prefix, kept defensively
    ("personality/prompts.py", 144), ("personality/prompts.py", 192), ("personality/prompts.py", 197),
    ("README.md", 21), ("README.md", 22), ("README.md", 23), ("README.md", 27),
    ("scripts/render_demo_gif.py", 2), ("scripts/render_demo_gif.py", 27), ("scripts/render_demo_gif.py", 52),
    ("site/src/components/DemoMock.astro", 7), ("site/src/data/demo-transcript.ts", 11),
    ("site/src/styles/global.css", 133), ("tests/test_formatters.py", 1),
    ("utils/embeds.py", 293), ("utils/formatters.py", 1), ("utils/formatters.py", 62),
})

def test_render_hits_are_all_allowlisted():
    root = _repo_root()
    offenders = []
    for path in _tracked_non_archive_files(root):
        rel = str(path.relative_to(root).as_posix())
        text = path.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), start=1):
            if re.search(r"\brender\w*\b", line, re.IGNORECASE) and (rel, i) not in RENDER_ALLOWLIST:
                offenders.append(f"{rel}:{i}")
    assert offenders == [], f"un-allowlisted Render reference(s): {offenders}"
```

**5. Positive control** (mirrors `test_drift_guard_actually_detects_a_mismatch`, lines
128-139) — inject a fake `Koyeb`/`Oracle` string into a `tmp_path` file, run it through the
real `_scan_for_zero_tolerance_terms` seam, assert it's caught:
```python
def test_drift_guard_actually_detects_koyeb(tmp_path):
    fake = tmp_path / "fake.py"
    fake.write_text("# deployed to Koyeb\n", encoding="utf-8")
    offenders = _scan_for_zero_tolerance_terms([fake])
    assert offenders, "scanner failed to catch a deliberately-reintroduced Koyeb reference"
```

**6. Negative control** (mirrors `test_drift_guard_accepts_the_canonical_url`, lines
142-151) — a clean file with no hosting terms produces zero offenders. Also add an explicit
"real repo passes" test mirroring `test_planning_tree_is_excluded_from_the_scan` (lines
173-187): assert `docs/superpowers/` files ARE tracked (so exclusion isn't vacuous) but ARE
absent from `_tracked_non_archive_files()`'s return — this is the D-10 guard-of-the-guard.

**7. File-existence bonus checks** (RESEARCH.md's "line count sanity check") — cheap, add as
a small extra test:
```python
def test_koyeb_doc_removed_and_docker_doc_present():
    root = _repo_root()
    assert not (root / "docs" / "DEPLOY-KOYEB.md").exists()
    assert (root / "docs" / "DEPLOY-DOCKER.md").exists()
```

**Imports pattern** (mirrors invite guard lines 30-37 — no project-specific imports needed
here beyond stdlib, since this guard has no `logic/` seam to import):
```python
from __future__ import annotations

import re
import subprocess
from pathlib import Path
```

---

### `docs/DEPLOY-DOCKER.md` (docs, request-response runbook)

**Analog:** `docs/DEPLOY-KOYEB.md` (179 lines, being `git rm`'d — read its header/structure
before deletion, do not copy its content wholesale per D-06).

**Structure to mirror** (from the read header, lines 1-19):
```markdown
# Dexter — Docker + Neon Run Guide

**Status:** ...
**Environment:** Docker Compose (residential/on-demand) + Neon serverless Postgres
**Cost:** ...
```
Reuse the "Status / Environment / Cost" front-matter convention (lines 3-5) but retarget
the Environment line away from "Koyeb free WEB service ... UptimeRobot keep-alive" to
"Docker Compose on your PC + Neon serverless Postgres" per D-07's exact relabeling.

**Section shape per D-06 / RESEARCH.md content plan** (~40-60 lines total, NOT the old file's
179): Title+status → Prereqs (Docker/Compose versions) → Setup steps (`cp .env.example .env`,
fill 4 vars, `docker compose up -d --build`) → Verify-alive (`curl :8000/health`, `docker
compose logs -f bot`) → Honest framing paragraph (residential/on-demand, not 24/7 — reuse
CLAUDE.md's existing "24/7 deploy PARKED" language) → single-Discord-token warning (carry
forward the old doc's "K-14 Break-Glass Rule" content, reworded, not the Koyeb specifics).

**Explicitly drop** (RESEARCH.md §6): Neon account walkthrough, UptimeRobot setup, Koyeb
secrets UI, HeavenCloud/Wispbyte contingency, archived-scripts table.

---

### `.env.example` (config, template reframe)

**Analog:** itself — full file read above (50 lines). This is a targeted reframe, not a
rewrite-from-scratch. Concrete line-level guidance:

- Line 7: `# Variable names are IDENTICAL in both environments (local .env and Koyeb secrets) — K-13.`
  → reword to Docker framing, **keep `K-13`**: e.g. `# Variable names are IDENTICAL in both environments (local .env and Docker) — K-13.`
- Lines 10, 23, 27: "KOYEB (production)" section header and inline "Koyeb encrypted Secret"
  language → relabel per D-07 as "DOCKER (on your PC + Neon)"; keep the local-Postgres-vs-Neon
  `DATABASE_URL` split (lines 18-27) structurally intact, just retarget the second branch's
  label.
- Line 30: `# DATABASE_URL is the ONLY value that differs between local and Koyeb environments.`
  → `# DATABASE_URL is the ONLY value that differs between local and Docker+Neon environments.`
- Lines 37-38: UptimeRobot inbound-keep-alive note referencing `docs/DEPLOY-KOYEB.md` → drop
  entirely (no scale-to-zero concept applies to a residential Docker run) OR repoint to
  `docs/DEPLOY-DOCKER.md` if any of that paragraph's content survives — but D-07 says drop the
  UptimeRobot-inbound language, so prefer deletion over repoint.
- Line 34 (`Bot-side outbound dead-man ping (K-09)`): **keep verbatim** — D-07 explicitly
  preserves the Healthchecks.io outbound note as host-agnostic.

---

### `config.py:22`, `Dockerfile:1-2`, `docker-compose.yml` (Oracle-era comment), `utils/logger.py:41`, `scripts/memory_spike.py`, `utils/embeds.py:294`, `tests/test_config.py`

**Analog / governing pattern:** the D-04 worked example itself (already locked in
CONTEXT.md and RESEARCH.md — no external code analog needed, this is a find-replace
discipline, not a code pattern):
```python
# BEFORE:
AUDIO_CACHE_MAX_MB = 512  # Koyeb 2GB ephemeral disk (K-07)
# AFTER:
AUDIO_CACHE_MAX_MB = 512  # 512MB cap on ephemeral disk (K-07)
```
**Rule for every one of these 7 files:** locate the hosting-term word/phrase, replace ONLY
that word/phrase, verify the adjacent `(K-##)` or `(D-##)` substring is byte-identical
post-edit (Pitfall 3 in RESEARCH.md — this is the single most likely execution mistake in
this phase). `utils/embeds.py:294` keeps `(D-19)` specifically (D-11):
```python
# BEFORE: # No Oracle/CPU label — baselines against actual run environment (D-19).
# AFTER:  # No host-CPU label — baselines against actual run environment (D-19).
```

---

### `bot.py` (~216-264, 578-589) — the `$PORT`-survivor pattern

**Analog:** RESEARCH.md's own worked before/after (reproduced verbatim, this IS the pattern
to copy):
```python
# BEFORE (bot.py:252-256):
try:
    # Render injects $PORT and routes its public URL to it; default 8000 keeps
    # Railway / PC / local working unchanged. The /health route + an external
    # pinger (UptimeRobot) is what keeps a Render free web service from sleeping.
    _health_port = int(os.environ.get("PORT", "8000"))
# AFTER (illustrative — exact wording is Claude's Discretion):
try:
    # $PORT is read for host portability; default 8000 keeps local/Docker
    # runs unchanged. The /health route lets an optional external uptime
    # pinger confirm the process is alive.
    _health_port = int(os.environ.get("PORT", "8000"))
```
Keep the actual `os.environ.get("PORT", "8000")` line and every `(K-02)`/`(K-04)`/`(K-05)`
tag in this range untouched — only prose is rewritten. Also reword the adjacent "Railway"
mention (RESEARCH.md A3, discretionary but recommended, same edit pass).

---

### `CLAUDE.md` (Tech Stack Hosting bullet, Phase-5 build log, Docker/Koyeb log-viewer note)

**Analog:** the file's own existing narrative style — this is the authoritative spec file
already being read/edited every phase; match its existing terse, hyphen-scarred prose style
(see the file's own "Hosting" bullet line 24 and Phase-5 section for the tone to preserve).
Reword lines 24, 687, 819, 820, 822 host-honest; keep tags at lines 309, 362, 687, 705, 921
per the K-## census (5 tags in this file: K-04×2, K-07×2, K-16).

---

### Deletions (no analog needed)

`scripts/archive/backup.sh`, `deploy.sh`, `keepalive.sh`, `lifecycle-policy.json` (D-02) and
`scripts/seed_restore_test.py` (D-11) — straightforward `git rm`, dead code, no pattern to
extract. Confirm via `git grep -l "backup.sh"` post-deletion that nothing else references
`scripts/backup.sh` (Pitfall 2 — this is exactly why `seed_restore_test.py` is included in
this deletion wave, not deferred).

---

## Shared Patterns

### `(K-##)`/`(D-##)` tag preservation (D-04)
**Source:** RESEARCH.md's worked example (`config.py:22`) — see excerpt above.
**Apply to:** every one of the 8 tag-bearing files (`bot.py`, `config.py`, `CLAUDE.md`,
`.env.example`, `Dockerfile`, `tests/test_config.py`, `utils/logger.py`,
`scripts/memory_spike.py`) plus the D-11 addition `utils/embeds.py` (`D-19` tag).
**Post-edit verification:** re-run the K-## census
(`git grep -noE "K-[0-9]{2}"` on tracked non-archive files) and confirm the count stays at
12 distinct tags across the 8 survivor files (3 tags — K-06, K-10, K-14 — correctly vanish
with `docs/DEPLOY-KOYEB.md`'s deletion; that's expected, not a regression).

### Sealed-archive exclusion (D-03/D-10)
**Source:** `tests/test_invite_drift_guard.py`'s `PLANNING_PREFIX` pattern (line 56),
extended to three prefixes.
**Apply to:** both the manual scrub pass (do not touch `.planning/`, `milestones/`,
`docs/superpowers/{plans,specs}/*`) and the new drift guard's `EXCLUDED_PREFIXES` tuple.

### Verification grep discipline (RESEARCH.md § Verification Grep Command)
**Source:** the two-part Part-1 (zero-tolerance Koyeb/Oracle) / Part-2 (Render allowlist
diff) shell script in RESEARCH.md, now also encoded as the drift-guard's two test functions
above.
**Apply to:** run after every scrub-target file edit (cheap, <1s) and again at wave/phase
gate, per RESEARCH.md's Sampling Rate section.

## No Analog Found

None — every new/modified file has at least a role-match or exact analog. The two
genuinely-new artifacts (drift guard, Docker doc) both have direct, recently-established
sibling files in this repo (invite/site drift guards; the just-deleted Koyeb doc's structure).

## Metadata

**Analog search scope:** `tests/` (drift guard precedents), `docs/` (deploy-doc precedent),
scrub-target files themselves (`config.py`, `bot.py`, `.env.example`, `docker-compose.yml`,
`Dockerfile`, `CLAUDE.md`, `utils/logger.py`, `utils/embeds.py`, `scripts/memory_spike.py`,
`tests/test_config.py`) — all already fully enumerated with file:line precision in
`24-RESEARCH.md`'s § Full Reference Inventory, so no additional Glob/Grep was needed beyond
confirming the two drift-guard analogs and the deleted doc's header shape.
**Files read this pass:** `tests/test_invite_drift_guard.py` (full, 265 lines),
`tests/test_site_drift_guard.py` (full, 144 lines), `docs/DEPLOY-KOYEB.md` (lines 1-40),
`.env.example` (full, 50 lines).
**Pattern extraction date:** 2026-07-15
