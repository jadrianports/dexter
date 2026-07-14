# Phase 23: Portfolio Surface & CI/CD - Pattern Map

**Mapped:** 2026-07-14
**Files analyzed:** 15 (new + modified)
**Analogs found:** 6 with strong procedural matches / 15 total (most are genuinely NO-ANALOG new-territory files — this is the repo's first frontend)

## Context

This phase is unlike any prior phase in the repo: it introduces the **first non-Python source tree** (`site/` — Astro/Node), the **first two new GitHub Actions workflows** since Phase 18's `ci.yml`, and a **README full rewrite** (currently 2 lines, effectively greenfield). There is close to zero in-repo UI/frontend precedent to copy. Consequently this PATTERNS.md is weighted toward **procedural/structural analogs** (how this repo writes workflows, how it writes drift-guard tests, how it writes pure `logic/` seams, how it disciplines Docker/secrets) rather than component-level analogs, per the orchestrator's explicit guidance for this phase.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `.github/workflows/ci.yml` (MODIFY — add site job) | config/CI | batch (build+test gate) | itself (existing file, extend in place) | exact |
| `.github/workflows/pages.yml` (NEW) | config/CI | event-driven (workflow_run) | `.github/workflows/ci.yml` (structure/comment discipline) | role-match (no Pages precedent exists) |
| `.github/workflows/release.yml` (NEW, name planner's call) | config/CI | event-driven (tag push) | `.github/workflows/ci.yml` (structure/comment discipline) + `Dockerfile` (what it packages) | role-match |
| `tests/test_site_drift_guard.py` (NEW) | test | CRUD/transform (file scan → assert) | `tests/test_invite_drift_guard.py` (near-exact structural sibling) | exact |
| `logic/invite.py` | (READ-ONLY consumer, not modified) | pure transform | — | n/a — reused as-is, never re-implemented |
| `config.py` (READ-ONLY consumer for the 3 constants) | config | — | — | n/a — reused as-is, mirrored (never re-derived) into `site/src/config.ts` |
| `site/astro.config.mjs` (NEW) | config | — | none in-repo (Astro-specific) | no analog |
| `site/package.json` / `package-lock.json` (NEW) | config | — | `requirements.txt`/`requirements-dev.txt` (role-equivalent: pinned dependency manifest) | role-match (different ecosystem) |
| `site/src/layouts/Layout.astro` (NEW) | component | request-response (SSG render) | none in-repo | no analog |
| `site/src/pages/index.astro` (NEW) | component (page composition) | request-response | none in-repo | no analog |
| `site/src/components/{Hero,DemoMock,DemoMessage,Features,FeatureCard,Boundaries,BoundaryItem,Cta,Footer}.astro` (NEW) | component | request-response | none in-repo | no analog |
| `site/src/data/demo-transcript.ts` (NEW) | model (static data) | transform | `personality/responses.py` / `personality/roasts.py` (role-match: hand-authored string pools consumed by a template layer) | role-match |
| `site/src/config.ts` (NEW) | config | — | `config.py` (role-match: the constant it mirrors) | role-match |
| `site/src/styles/global.css` (NEW) | config/style | — | none in-repo | no analog |
| `scripts/render_demo_gif.py` (NEW) | utility | file I/O (Playwright capture → ffmpeg convert) | `scripts/seed_restore_test.py`, `scripts/backup.sh` (ops scripts: standalone, dev-machine-run, not imported by app code) | role-match |
| `README.md` (MODIFY — full rewrite) | docs | transform | itself (2-line current version — effectively greenfield) | no analog (content), exact (location) |
| `.gitignore` / `.dockerignore` (MODIFY — add `node_modules/`, `site/dist/`, `site/`) | config | — | itself (existing files, extend in place) | exact |
| `23-HUMAN-UAT.md` (NEW, at phase close) | docs | — | `22-HUMAN-UAT.md`, `20-HUMAN-UAT.md`, `16-HUMAN-UAT.md` (established acknowledged-deferred pattern) | exact |

## Pattern Assignments

### `.github/workflows/ci.yml` (MODIFY — new site job)

**Analog:** itself (`.github/workflows/ci.yml`, read in full above)

**Structure to replicate exactly** (comment discipline + trigger + permissions ceiling):
```yaml
name: CI

# CICD-01: pytest + Ruff gate, blocking on every push and pull_request.
# Deliberately the safe PR trigger below, NEVER its "_target" variant — the latter
# would run a forked PR's untrusted code with write/secret access (T-18-CIPRIV).
# Top-level `permissions: contents: read` denies write even to the default GITHUB_TOKEN.
on:
  push:
  pull_request:

permissions:
  contents: read # least-privilege — this workflow only reads code and runs tests/lint
```

**New job to add — same file, sibling to `test:`, unprivileged (per D-03, the scan MUST stay in `ci.yml`)**:
```yaml
  site:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: site
    steps:
      - uses: actions/checkout@v7   # RESEARCH.md Finding 4: bump from ci.yml's current @v4, low-priority
      - uses: actions/setup-node@v7
        with:
          node-version: "22"
          cache: "npm"
          cache-dependency-path: site/package-lock.json
      - run: npm ci
      - run: npm run build
      - name: Drift-scan the built artifact
        working-directory: .
        env:
          SITE_DIST_REQUIRED: "1"   # D-02: must never silently skip in CI
        run: pytest -q tests/test_site_drift_guard.py
```

**Comment-discipline convention to copy:** every non-obvious step in `ci.yml` carries an inline `#` comment naming *why*, often citing a decision/pitfall ID (`Pitfall 7`, `T-18-CIPRIV`, `D-15`). The new site job's `SITE_DIST_REQUIRED` line should get the same treatment (cite D-02 directly, as shown).

**Retire Pitfall 7's comment** (lines 47-52 above) per RESEARCH.md Finding 6 — the risk it warns about did not materialize on the real CI run; D-13's push-and-repair task is the natural place to delete the stale comment, not this file's site-job addition.

---

### `.github/workflows/pages.yml` (NEW)

**Analog:** `.github/workflows/ci.yml` for structural/comment conventions; no in-repo Pages precedent exists (first Pages workflow in the repo).

**Permissions-ceiling pattern to copy from `ci.yml`** (comment format, not the values — this file needs the *opposite* ceiling):
```yaml
permissions:
  contents: read
  pages: write
  id-token: write
```

**Full recommended skeleton** (from RESEARCH.md Finding 4, already vetted against `workflow_run` footguns):
```yaml
name: Deploy Pages

on:
  workflow_run:
    workflows: ["CI"]          # must match ci.yml's `name:` field exactly
    types: [completed]

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  deploy:
    if: >
      github.event.workflow_run.conclusion == 'success' &&
      github.event.workflow_run.head_branch == 'main'
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ github.event.workflow_run.head_sha }}   # NEVER rely on default checkout ref here
      - uses: actions/setup-node@v7
        with:
          node-version: "22"
          cache: "npm"
          cache-dependency-path: site/package-lock.json
      - run: npm ci
        working-directory: site
      - run: npm run build
        working-directory: site
      - uses: actions/upload-pages-artifact@v5
        with:
          path: site/dist
      - uses: actions/deploy-pages@v5
        id: deployment
```

**Comment discipline to preserve:** explain *why* `workflow_run` (not `needs:`) is used — cite D-03/D-12 the same way `ci.yml` cites T-18-CIPRIV, so a future reader doesn't wonder why the "simpler" option wasn't used (RESEARCH.md explicitly recommends this).

---

### `.github/workflows/release.yml` (NEW — name is planner's call)

**Analog:** `.github/workflows/ci.yml` for structure; `Dockerfile` for what it packages (read in full above — multi-arch header comment already exists, unchanged by this phase).

**Permissions-ceiling pattern (own file, per D-16 — `packages: write` must never enter `ci.yml`):**
```yaml
permissions:
  contents: read
  packages: write
```

**Full recommended skeleton** (from RESEARCH.md Finding 5):
```yaml
name: Release Image

on:
  push:
    tags: ["v*"]

permissions:
  contents: read
  packages: write

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: docker/setup-qemu-action@v4
      - uses: docker/setup-buildx-action@v4
      - uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/metadata-action@v6
        id: meta
        with:
          images: ghcr.io/jadrianports/dexter
          tags: |
            type=semver,pattern={{version}}
            type=raw,value=latest
      - uses: docker/build-push-action@v7
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

**Dockerfile discipline preserved unchanged** — the file this workflow builds already carries its own header comment (line 1-3 above) about multi-arch intent and secrets-at-runtime (T-04-05). This workflow must not bake any secret into a layer — `docker/login-action` uses `secrets.GITHUB_TOKEN` only, matching the existing "no baked secrets" discipline.

---

### `tests/test_site_drift_guard.py` (NEW)

**Analog:** `tests/test_invite_drift_guard.py` (read in full above — this is the load-bearing reuse of the whole phase).

**Reused directly (import, do not duplicate):**
```python
from tests.test_invite_drift_guard import _canonical_url, _collect_offenders
```
(If cross-test-module import proves awkward given `pyproject.toml`'s pytest import-mode, the fallback — per RESEARCH.md — is extracting `URL_PATTERN`, `_canonical_url`, `_collect_offenders` into a leading-underscore helper module, e.g. `tests/_url_scan.py`, imported by both files. Either way: **never re-derive the regex**.)

**Core pattern to copy — env-var-gated skip/fail split** (this IS the fix for D-02's "must never silently skip in CI" requirement):
```python
import os
from pathlib import Path
import pytest

SITE_DIST_DIR = Path("site/dist")

def _dist_html_files(dist_dir: Path) -> list[Path]:
    if not dist_dir.exists():
        return []
    return list(dist_dir.rglob("*.html"))

def test_no_drift_in_built_site():
    files = _dist_html_files(SITE_DIST_DIR)
    if not files:
        if os.getenv("SITE_DIST_REQUIRED"):
            pytest.fail(
                "site/dist/ is empty but SITE_DIST_REQUIRED=1 — "
                "the Astro build step did not run or produced no output"
            )
        pytest.skip("site/dist/ not built (local run, no `npm run build`)")
    offenders = _collect_offenders(files, _canonical_url())
    assert offenders == [], f"drifted invite URL(s) in built site: {offenders}"
```

**Mandatory positive control** (mirrors `test_drift_guard_actually_detects_a_mismatch` in the analog file, lines 128-139 above — same shape, different file-collection source):
```python
def test_dist_drift_guard_actually_detects_a_mismatch(tmp_path):
    fake_html = tmp_path / "index.html"
    fake_html.write_text(
        '<a href="https://discord.com/oauth2/authorize?client_id=999&permissions=8&scope=bot">Add</a>',
        encoding="utf-8",
    )
    offenders = _collect_offenders([fake_html], _canonical_url())
    assert offenders, "dist/ scanner failed to catch a deliberately-wrong invite URL"
```

**What NOT to copy from the analog:** `_tracked_doc_files()`'s `git ls-files` + `TEXT_EXTENSIONS`/`PLANNING_PREFIX` filtering does not apply — `dist/` is never git-tracked, so this needs a filesystem walk (`Path.rglob`), not a `git ls-files` filter. Do not port the extension-allowlist logic; it solves a different problem (source-file discovery) than this file's problem (built-artifact discovery).

**Docstring/comment convention to copy:** the analog's module docstring (lines 1-28) states the guarantee, names the vacuous-pass risk, and names the positive control that disproves it, with an explicit Task-numbered test list. Follow the same shape — state plainly that this file's guarantee only covers static build-time text (per the "HARD VERIFICATION GATE" residual risk noted in 23-UI-SPEC.md, a client-side-JS-constructed URL would not be caught).

---

### `logic/invite.py::build_invite_url` (READ-ONLY — the single constructor, never touched)

**File in full (read above).** Key facts for downstream consumers:
- Signature: `build_invite_url(*, client_id: int, permissions_value: int, scopes: tuple[str, ...] = ("bot", "applications.commands")) -> str`
- Wraps `discord.utils.oauth_url(client_id, permissions=discord.Permissions(permissions_value), scopes=scopes)`
- **Astro cannot import this** (no Python interop) — `site/src/config.ts` necessarily contains a second literal string, but it MUST be sourced from the same three `config.py` constants (mirrored, never re-derived) and is guarded by the D-02 CI scan. This is documented explicitly in 23-UI-SPEC.md's "Invite URL Sourcing (HARD FENCE)" section — treat that section as load-bearing spec, not optional color.

**`config.py` constants being mirrored** (verified at HEAD, lines noted):
```python
# config.py:282
DISCORD_CLIENT_ID = int(os.getenv("DISCORD_CLIENT_ID") or "1492588698364018898")
# config.py:300
INVITE_PERMISSIONS_VALUE = 309240908864
# config.py:304
INVITE_SCOPES: tuple[str, ...] = ("bot", "applications.commands")
```

**Canonical string that must appear byte-identical in the built HTML** (already computed and locked by 23-UI-SPEC.md):
```
https://discord.com/oauth2/authorize?client_id=1492588698364018898&scope=bot+applications.commands&permissions=309240908864
```

**test_logic_invite_is_the_only_url_constructor (in the analog file, lines 240-256)** — a hardcoded, reviewable marker-tuple scan of every tracked `.py` file (excluding `tests/`/`.planning/`) asserting only `logic/invite.py` contains `oauth_url(` or the literal domain string. **This test's existence is why Phase 23 code must call `build_invite_url`, never hand-build a URL in any new Python file** (it does not, and cannot, cover the new `.ts`/`.astro` files — that's exactly why D-02's separate `dist/` scan exists).

---

### `scripts/render_demo_gif.py` (NEW)

**Analog:** `scripts/seed_restore_test.py`, `scripts/backup.sh`, `scripts/deploy.sh` — all standalone, dev-machine/ops-run scripts, never imported by app code, never added to `requirements.txt`.

**Pattern to follow:** a header comment documenting one-time manual setup (mirrors the `ci.yml` Pitfall-7 comment style — state the setup command explicitly, e.g. `pip install playwright && playwright install chromium`), then a `sync_playwright()` context manager per RESEARCH.md Finding 7:
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(
        record_video_dir="scratch/videos/",
        record_video_size={"width": 900, "height": 560},
    )
    page = context.new_page()
    page.goto("file:///.../site/dist/index.html")
    page.wait_for_timeout(6000)
    context.close()   # video only finalizes on close()
    print(page.video.path())
```
Followed by an `ffmpeg` two-pass palette conversion (already a project dependency, but this conversion step runs on a dev machine, not in CI or the Docker image):
```bash
ffmpeg -i demo.webm -vf "fps=12,scale=640:-1:flags=lanczos,palettegen=stats_mode=diff" palette.png
ffmpeg -i demo.webm -i palette.png -filter_complex \
  "fps=12,scale=640:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5" \
  docs/demo.gif
```

**Dependency-placement rule to enforce (per Finding 7):** Playwright must NOT enter `requirements.txt` or `requirements-dev.txt` — mirror the existing discipline that `requirements-dev.txt` stays intentionally minimal (currently only `ruff`). Document the one-time `pip install playwright` in the script's own header comment instead, exactly the way `ci.yml`'s Pitfall-7 comment documents a conditional manual step without baking it into the default path.

---

### `README.md` (MODIFY — full rewrite)

**Current file (read in full above — all 2 lines):**
```markdown
# dexter
discord music bot with ai personality
```

**No structural analog exists in-repo** (this is the first substantive README content). Use 23-UI-SPEC.md's Copywriting Contract + D-08's mid-depth structure (tagline → badges → demo GIF → feature list → mermaid diagram → 3-4 hard-problem callouts → honest boundaries → invite link) as the spec-of-record; do not invent new structure here.

**Badge markdown (from RESEARCH.md Finding 8, exact URL forms):**
```markdown
[![CI](https://github.com/jadrianports/dexter/actions/workflows/ci.yml/badge.svg)](https://github.com/jadrianports/dexter/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.3%2B-5865F2?logo=discord&logoColor=white)
![Postgres](https://img.shields.io/badge/postgres-pgvector-336791?logo=postgresql&logoColor=white)
![Gemini](https://img.shields.io/badge/gemini-2.5--flash-4285F4?logo=googlegemini&logoColor=white)
```
**Sequencing constraint carried from RESEARCH.md:** the CI badge only renders real status after D-13's push lands and a real CI run completes at HEAD — do not finalize/screenshot README copy claiming "green CI" before that run exists.

**PORT-04 boundary wording** — source verbatim from 23-UI-SPEC.md's Copywriting Contract table (Boundary 1-4 rows) for the landing-page short form; expand per D-10's fuller README framing, sourcing the memory-scoping wording from `.planning/PROJECT.md` §Key Decisions (the shipped reality, not the hypothesis) as CONTEXT.md instructs.

---

## Shared Patterns

### Workflow file comment discipline
**Source:** `.github/workflows/ci.yml` (every file in this phase should match this convention)
**Apply to:** `pages.yml`, `release.yml`, and the new job block added to `ci.yml`
```yaml
# Deliberately the safe PR trigger below, NEVER its "_target" variant — the latter
# would run a forked PR's untrusted code with write/secret access (T-18-CIPRIV).
permissions:
  contents: read # least-privilege — this workflow only reads code and runs tests/lint
```
Every non-obvious YAML line gets an inline comment citing the decision ID it implements (D-02, D-03, D-12, D-16). This is not optional style — it is how every other workflow-adjacent file in this repo self-documents its own safety reasoning (see also Dockerfile's header, `tests/test_invite_drift_guard.py`'s module docstring).

### Drift-guard reuse discipline (do not duplicate the regex)
**Source:** `tests/test_invite_drift_guard.py::URL_PATTERN`, `_canonical_url()`, `_collect_offenders()`
**Apply to:** `tests/test_site_drift_guard.py`
Import or extract-to-shared-module; never hand-roll a second regex. The two files should differ ONLY in file-collection strategy (`git ls-files`+extension-allowlist vs `Path.rglob("*.html")` on a build directory) — the URL-matching and comparison logic is identical and must stay a single source of truth.

### Zero-secrets-in-CI posture
**Source:** `.github/workflows/ci.yml` (`TEST_DATABASE_URL` only, no Gemini key — comment at lines 34-37), `config.py`'s `DISCORD_CLIENT_ID`/`INVITE_PERMISSIONS_VALUE` being public committed constants (Phase 22 D-04, explicitly "so CI, with no secrets, can build the URL")
**Apply to:** `pages.yml` (no new secrets — `GITHUB_TOKEN`'s auto-scoped `pages`/`id-token` permissions suffice), `release.yml` (`docker/login-action` uses `secrets.GITHUB_TOKEN` only, never a new PAT — this is also why GHCR visibility (D-17) is a manual HUMAN-UAT step rather than automated: automating it would require a new PAT, breaking this posture)

### Secrets-never-in-image discipline
**Source:** `Dockerfile` header comment (lines 1-3) + `.dockerignore` header comment ("Security: .env (real secrets) must never enter a Docker layer (T-04-05)")
**Apply to:** any Docker-adjacent change in `release.yml` — the image built and pushed here is byte-identical in security posture to the existing `Dockerfile`; this phase changes nothing about how secrets reach the running container (still runtime env vars only).

### Acknowledged-deferred HUMAN-UAT pattern
**Source:** `.planning/phases/22-invite-plumbing/22-HUMAN-UAT.md`, `.planning/phases/20-.../20-HUMAN-UAT.md`, `.planning/phases/16-.../16-HUMAN-UAT.md` (established since Phase 11)
**Apply to:** `23-HUMAN-UAT.md` — must carry at minimum: (1) D-17's GHCR public-visibility flip + logged-out `docker pull` verification, (2) the one-time manual "Settings → Pages → Build and deployment → Source: GitHub Actions" toggle (RESEARCH.md Finding 4 — confirmed a real prerequisite, not automatable without a new PAT), (3) PORT-02's verbatim Dexter line sourcing if not already supplied by the time of phase close (RESEARCH.md Finding 1 confirms `logs/dexter.log` cannot supply it — this is a real, not hypothetical, human item).

### Pure-seam convention (`logic/`) — NOT directly applicable but worth noting as a boundary
**Source:** `logic/invite.py` docstring (lines 9-27) explicitly documents its own deviation from the repo's "no discord import in logic/" convention (Phase 10 D-01/D-02).
**Relevance to this phase:** no new `logic/` file is created by Phase 23 (confirmed — CONTEXT.md's file list is entirely `site/`, workflows, tests, README, scripts). If the planner ever considers adding one (e.g. a Python-side helper for the GIF pipeline), it should follow this same "document any convention deviation explicitly" discipline rather than silently breaking the pure-seam rule.

## No Analog Found

Files with no close match in the codebase — first-of-their-kind for this repo. Planner should use 23-UI-SPEC.md (design contract) and 23-RESEARCH.md (Findings 2/4/5/7, Architecture Patterns, Code Examples) as the primary reference for these, not an in-repo analog:

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `site/astro.config.mjs` | config | — | First Astro/SSG config in the repo; must set both `site:` and `base: '/dexter'` per Finding 2 — no in-repo precedent for subpath-aware static-site config |
| `site/src/layouts/Layout.astro` | component | request-response | First `.astro` file in the repo; no HTML-templating layer exists elsewhere (all prior output is Discord embeds via `utils/embeds.py`, a structurally different rendering target) |
| `site/src/pages/index.astro` | component | request-response | Same — first page-composition file |
| `site/src/components/*.astro` (9 files) | component | request-response | Same — hand-authored HTML/CSS components with zero registry (per 23-UI-SPEC.md Design System table, shadcn/Radix explicitly ruled out as inapplicable) |
| `site/src/styles/global.css` | config/style | — | First stylesheet in the repo (Discord embeds have no CSS concept) |
| `site/package.json` / `package-lock.json` | config | — | First Node dependency manifest; role-equivalent to `requirements.txt` but a different ecosystem with different lockfile semantics (`npm ci` requires the lockfile to exist, unlike `pip install -r`) |

## Metadata

**Analog search scope:** `.github/workflows/`, `tests/test_invite_*.py`, `logic/invite.py`, `config.py`, `Dockerfile`, `.gitignore`, `.dockerignore`, `scripts/`, `README.md`, `personality/responses.py` (referenced for role-match only)
**Files scanned:** 8 read in full, 1 grepped for constants
**Pattern extraction date:** 2026-07-14
