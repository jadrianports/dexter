---
phase: 23
slug: portfolio-surface-ci-cd
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-14
---

# Phase 23 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `23-RESEARCH.md` §Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (per `requirements.txt`); Node/Astro build (`npm run build`) for the site artifact |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) — existing, unchanged except the new `tests/test_site_drift_guard.py` module |
| **Quick run command** | `ruff check . && ruff format --check . && pytest tests/test_invite_drift_guard.py tests/test_site_drift_guard.py -q` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | quick: ~10s · full: ~7 min locally (1036 passed / 124 skipped / 0 failed at HEAD, verified 2026-07-14); faster in CI against the `pgvector` service container |

**Phase-specific note:** this phase's headline deliverables (Pages deploy, GHCR publish, CI badge) are
**only truly provable in real CI** — a locally-green suite does not satisfy PORT-03's "the badge reflects
the actual last run." The D-13 push is therefore both the first task and the first validation event.

---

## Sampling Rate

- **After every task commit:** `ruff check . && ruff format --check .` + the narrowest relevant pytest slice
- **After every plan wave:** `pytest -q` (full suite)
- **Before `/gsd-verify-work`:** full suite green **in actual CI**, not only locally
- **Max feedback latency:** ~10s (quick) / ~7 min (full)

---

## Per-Task Verification Map

> Task IDs are assigned by the planner. This map is keyed by requirement + surface; the planner
> MUST attach each row to a concrete task ID and may add rows, but may not drop a row.

| Surface | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| Push Phases 19–22 to `origin/main`; CI green at HEAD | TBD | 1 | (D-13 prereq for PORT-03, CICD-02/03) | — | Four unexercised phases pass the existing gate before new CI surface is added | integration (real CI) | `gh run watch` on the push; `ruff format .` applied first (3 files known-red) | ✅ existing `ci.yml` | ⬜ pending |
| Astro site builds; `base: '/dexter'` correct | TBD | TBD | PORT-01 | — | N/A | integration | `cd site && npm ci && npm run build` exits 0; `dist/index.html` asset paths are `/dexter/…` | ❌ W0 | ⬜ pending |
| **`dist/*.html` invite-URL drift scan** | TBD | TBD | PORT-01, CICD-02 (regression) | T-23-DRIFT | A drifted/over-privileged OAuth2 URL in the shipped artifact **fails the build**; never silently skips in CI | unit + CI-required | `SITE_DIST_REQUIRED=1 pytest tests/test_site_drift_guard.py -v` | ❌ W0 | ⬜ pending |
| **Positive control** for the `dist/` scanner | TBD | TBD | PORT-01 (guard integrity) | T-23-DRIFT | Scanner provably finds a URL when one exists → a broken regex cannot green-vacuous-pass | unit | `pytest tests/test_site_drift_guard.py -k positive_control -v` | ❌ W0 | ⬜ pending |
| Existing invite drift guard stays green **and non-vacuous** | TBD | TBD | (Phase 22 regression) | T-23-DRIFT | Phase 22's guarantee survives the SSG migration | unit | `pytest tests/test_invite_drift_guard.py -v` | ✅ exists | ⬜ pending |
| Demo mock renders; transcript is **verbatim** Dexter output | TBD | TBD | PORT-02 | T-23-HONEST | No roast line is authored by an executor; every line traces to the user-supplied source in `23-HUMAN-UAT.md` | **manual-only** | N/A — code review + diff against the human-supplied lines | ❌ W0 | ⬜ pending |
| README GIF rendered from the mock (one source, two derivatives) | TBD | TBD | PORT-02, PORT-03 | — | N/A | script + manual | `python scripts/render_demo_gif.py` produces a ≤2MB GIF; visual check | ❌ W0 | ⬜ pending |
| README case study: tagline, 5 badges, mermaid, callouts, invite link | TBD | TBD | PORT-03 | — | N/A | **manual-only** (GitHub's own markdown/mermaid renderer) | N/A — view the rendered README on github.com | ❌ W0 | ⬜ pending |
| CI badge points at the real `ci.yml` run and is green | TBD | TBD | PORT-03 | — | N/A | manual (post-push) | Badge URL resolves to a green run on `main` at HEAD | ❌ W0 | ⬜ pending |
| Four PORT-04 boundaries present on **both** surfaces, matching shipped reality | TBD | TBD | PORT-04 | T-23-HONEST | Disclosure describes what **shipped** (PROJECT.md §Key Decisions), not the hypothesis | code review + grep | Grep landing-page source + README for each of the 4 boundaries; diff wording against `.planning/PROJECT.md` §Key Decisions | ❌ W0 | ⬜ pending |
| `pages.yml` deploys `/site` to Pages on merge to `main` | TBD | TBD | CICD-02 | T-23-CIPRIV | Elevated (`pages: write` + `id-token: write`) job lives in its **own** workflow, never in PR-triggered `ci.yml`; no `pull_request_target` anywhere | integration (real CI) | Actions tab shows a green `pages.yml` run after a merge to `main`; site loads at `jadrianports.github.io/dexter` | ❌ W0 | ⬜ pending |
| Pages deploy is **really gated** on CI green (not advisory) | TBD | TBD | CICD-02 | T-23-CIPRIV | A red `ci.yml` on `main` must **not** publish a page carrying a drifted invite URL | integration | `workflow_run` filtered on `conclusion == success` **and** `head_branch == 'main'`, checking out `head_sha`; prove by observing a red-CI run publishes nothing | ❌ W0 | ⬜ pending |
| `release.yml` publishes multi-arch GHCR image on `v*` tag | TBD | TBD | CICD-03 | T-23-SUPPLY | `packages: write` scoped to its own workflow; secrets never baked into layers (T-04-05); `site/`+`node_modules/` excluded via `.dockerignore` | integration (real CI) | Tag `v1.4.0` → green run; `docker manifest inspect ghcr.io/jadrianports/dexter:v1.4.0` lists amd64 + arm64 | ❌ W0 | ⬜ pending |
| Image pullable with **zero build step**, logged out | TBD | TBD | CICD-03 | — | N/A | **manual-only** (D-17 — GHCR visibility is a UI setting) | `docker logout ghcr.io && docker pull ghcr.io/jadrianports/dexter:v1.4.0` | ❌ W0 | ⬜ pending |
| No second invite-URL constructor / shortener / redirect | TBD | TBD | (Phase 22 D-07 fence) | T-23-DRIFT | `logic/invite.py::build_invite_url()` remains the sole constructor | code review + grep | Grep repo for `discord.com/oauth2/authorize` outside `logic/invite.py`, tests, and generated `dist/` | ✅ exists | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Every surface in this phase is net-new. No existing test infrastructure covers any of it.

- [ ] `site/` — the entire Astro project (`package.json`, `package-lock.json`, `astro.config.mjs`, `src/pages/index.astro`, components) — PORT-01, PORT-02
- [ ] `tests/test_site_drift_guard.py` — the D-02 `dist/*.html` artifact scan **+ its positive control** (extends, does not duplicate, `tests/test_invite_drift_guard.py`'s regex)
- [ ] `.github/workflows/pages.yml` — CICD-02
- [ ] `.github/workflows/release.yml` (or planner-chosen name) — CICD-03
- [ ] `README.md` rewrite — currently 2 lines — PORT-03, PORT-04
- [ ] `scripts/render_demo_gif.py` — D-07 Playwright→GIF pipeline
- [ ] `23-HUMAN-UAT.md` — carries the three genuinely-human items (below)
- [ ] `.gitignore` / `.dockerignore` — must exclude `site/node_modules/`, `site/dist/`; `site/` must never enter the bot image

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| **Supply the verbatim Dexter transcript** for the demo mock | PORT-02 | `logs/dexter.log` **structurally cannot** provide it — `services/gemini.py::chat()` logs `len(response.text)`, never the text, at every call site. And the honesty rule (D-06) forbids an executor writing the lines. | User pastes a handful of real Dexter responses (`/roast`, `/ask`, `/play`, ambient) from Discord into `23-HUMAN-UAT.md`. ~1 minute. The mock's transcript must match them **byte-for-byte**. |
| **Enable GitHub Pages** (Settings → Pages → Source = GitHub Actions) | CICD-02 | Repo setting. (`actions/configure-pages` with `enablement: true` can do it under conditions — the planner should attempt that first and fall back to this item.) | Repo Settings → Pages → Build and deployment → Source: **GitHub Actions**. |
| **Flip the GHCR package to public**, then verify a logged-out pull | CICD-03 (D-17) | GHCR packages are private by default; visibility is a GitHub UI setting on the package page and genuinely cannot be set from the publishing workflow on first push. | Package page → Package settings → Change visibility → Public. Then: `docker logout ghcr.io && docker pull ghcr.io/jadrianports/dexter:v1.4.0` must succeed. |
| **README renders correctly on GitHub** (badges + mermaid) | PORT-03 | GitHub's markdown/mermaid renderer is not reproducible locally. | View the rendered README on github.com after the push; all 5 badges resolve, the mermaid diagram renders. |
| **Landing page visual/copy review** | PORT-01, PORT-04 | Taste + honesty are not assertable. | Load `jadrianports.github.io/dexter`; confirm the four PORT-04 boundaries read as *disclosure*, not apology; confirm the hosting caveat sits **before** the closing CTA (D-05). |

*(These follow the acknowledged-deferred HUMAN-UAT pattern used since Phase 11.)*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or a Wave 0 dependency
- [ ] Sampling continuity: no 3 consecutive tasks without an automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s (quick) / < 7min (full)
- [ ] The `dist/` scan **fails the build on drift** and **cannot silently skip in CI** (`SITE_DIST_REQUIRED=1`)
- [ ] The `dist/` scan has a **positive control** (Phase 22 D-10 discipline)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
