# Phase 23: Portfolio Surface & CI/CD - Research

**Researched:** 2026-07-14
**Domain:** Static site generation (Astro) + GitHub Actions CI/CD (Pages deploy, GHCR multi-arch publish) for a Python Discord bot repo
**Confidence:** HIGH (workflow mechanics, version numbers, PyPI wheel availability, log-content finding, local suite result — all tool-verified) / MEDIUM (exact Astro project layout, GIF pipeline tuning — reasonable but not exhaustively load-tested)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (do NOT relitigate — research is about HOW, not WHETHER)

- **D-01:** Landing page is an **Astro** static site in `/site` (user overrode Claude's hand-rolled-HTML recommendation). Zero JS by default. Costs accepted: Node toolchain enters the repo, Pages workflow gains a build step, drift guard breaks by construction unless D-02 ships.
- **D-02 (load-bearing):** Drift guard preserved by **building the site in CI and scanning `dist/*.html`** for `discord.com/oauth2/authorize…` URLs, asserting each equals `build_invite_url()`'s output. CI-only (needs a Node build). Must **fail the build on drift**, must **never silently skip in CI**. This also is asserted to close Phase 22's deferred **IN-01** (extension-allowlist gap) — planner must confirm genuinely discharged, not bypassed.
- **D-03 (locked topology):** Drift **scan** lives in `ci.yml` (unprivileged, runs on every push + PR, `contents: read` only). Pages **deploy** lives in its own `pages.yml` (privileged, `pages: write` + `id-token: write`, push-to-main only). Never bolt the privileged job into `ci.yml` behind an `if:` guard.
- **D-04:** Dark, terminal-ish, in Dexter's voice (page copy). Sarcasm in copy, never in structure — page stays legible/professional.
- **D-05:** Single scroll: hero → demo → features → honest boundaries (PORT-04, immediately before closing CTA) → CTA. Add-to-Discord button appears twice (hero + closing CTA). No on-page deep architecture section — links to README instead.
- **D-06 (load-bearing, reversed an earlier decision):** Demo is a **styled HTML/CSS mock of a Discord conversation**, NOT a screen recording, built from **verbatim, unedited, real Dexter output**. Never write the roast lines. Researcher was told to check `logs/dexter.log` first — **see Finding 1 below, this is resolved**.
- **D-07:** README gets its own small `.gif` rendered from the D-06 mock via Playwright. One source, two derivatives.
- **D-08:** README mid-depth: tagline → badges → demo GIF → feature list → mermaid diagram of cog→service→logic layering → 3-4 "hard problem" callouts → honest boundaries → invite link.
- **D-09:** Professional engineering prose in README; Dexter quoted only where he is the subject (demo, example outputs, maybe tagline). PORT-04 disclosure reads as disclosure, not a joke.
- **D-10:** PORT-04 boundaries appear on **both** landing page (before CTA, per D-05) and README, framed as constraint → deliberate decision. Four boundaries: 100-guild wall, on-demand hosting, full-savage + reactive kill-switch, hybrid memory scoping (**read PROJECT.md §Key Decisions for the shipped wording**, not the hypothesis).
- **D-11:** Pages publishes via `actions/deploy-pages` + `upload-pages-artifact`. No build output ever committed.
- **D-12:** Pages deploy **must be gated on the CI gate being green** — a merge to main that breaks the drift guard or tests must not publish a landing page with a wrong invite URL. Implementation (`workflow_run` vs `needs:`) is planner's call, but the gate must be real. **See Finding 4 below — `workflow_run` is not just preferred, it is structurally forced by D-03's file split.**
- **D-13 (hard blocker, corrected):** The 143 (now 144)-commit push is the **first task** of the phase, before any Phase 23 code. CI has run before (green at Phase 18, `gh run list` confirms 3 runs, 1 failure then 2 green) — it has simply never seen Phases 19-22. Pitfall-7's davey/PyNaCl warning is **retired** (real run succeeded) — **see Finding 6, confirmed and a concrete new finding added: `ruff format --check` WILL fail at HEAD today, but the full local pytest suite IS green.**
- **D-14:** Landing page lives at default `jadrianports.github.io/dexter` (project-page subpath). Astro `base: '/dexter'` + `site:` config required — **see Finding 2**.
- **D-15:** Five README badges: CI status, Python, discord.py, Postgres/pgvector, Gemini. **No license badge** (no LICENSE file).
- **D-16:** GHCR publishes on `v*` git tag, multi-arch (`linux/amd64` + `linux/arm64`) via buildx + QEMU. Needs `packages: write` → own workflow file, never `ci.yml`. Tagging `v1.4.0` → `ghcr.io/jadrianports/dexter:v1.4.0` + `:latest`.
- **D-17:** GHCR package flipped **public by hand** — genuinely cannot be done from the publishing workflow on first push (confirmed, Finding 5). Recorded as a `23-HUMAN-UAT.md` item: flip visibility, then verify `docker pull` succeeds from a logged-out shell.

### Claude's / Planner's Discretion

- How the D-02 `dist/` scan is invoked (pytest-shells-out-and-skips-when-absent vs standalone script step) — constraint: must fail on drift, must never silently skip in CI, positive-control test required.
- Whether `tests/test_invite_drift_guard.py` is extended or a sibling check added — reuse the regex/`.planning/`-exclusion logic, don't duplicate.
- Exact Astro project layout, `package.json` scripts, Node version pinning in CI.
- Mock demo's animation mechanism (CSS keyframes vs scroll/reveal) — should honor `prefers-reduced-motion`.
- Playwright render pipeline for the README GIF (resolution, frame rate, duration, `scripts/` location). Target: ~1-2MB, crisp text.
- Exact mermaid diagram content + which 3-4 hard-problem callouts make the cut.
- Exact copy for landing page / hero / disclosure section.
- Workflow file names and job granularity (`pages.yml` + a GHCR workflow name are the planner's call).
- GHCR tag set beyond `:v*` + `:latest` (e.g. `:sha`).
- How the D-13 CI-repair contingency is structured (dedicated first plan vs a gating task in plan 01).

### Deferred Ideas (OUT OF SCOPE — do not build)

- A real screen-recorded demo (`.webm`) of the running bot — rejected in favor of D-06's mock.
- A `LICENSE` file + license badge.
- A custom domain for the landing page.
- A prod auto-deploy of the bot (no prod host this milestone).
- `/permcheck` runtime permission-gap self-diagnostic (carried from Phase 22).
- A vanity/short invite link (ruled out by Phase 22 D-07 — defeats the literal-match drift guard).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PORT-01 | Static landing page in `/site` (hero, feature showcase, Add to Discord button) | Finding 2 (Astro `base`/`site` config), Architecture Patterns §Astro project layout, Pitfalls §Astro subpath |
| PORT-02 | Short demo showing personality landing, embedded in the page (reinterpreted as HTML/CSS mock, D-06) | **Finding 1 (dexter.log does NOT contain real generated output — confirmed by code inspection, not just absence)** — this determines the HUMAN-UAT scope |
| PORT-03 | README rewritten as architecture case study | Finding 8 (badge markdown), Code Examples §mermaid, Standard Stack §Playwright GIF pipeline |
| PORT-04 | Four scope boundaries disclosed honestly | PROJECT.md §Key Decisions is the source of truth for the shipped memory-scoping wording (already read and quoted below) |
| CICD-02 | `/site` auto-deploys to Pages on merge to main | Finding 4 (workflow_run gating), Code Examples §pages.yml, Architecture Patterns §CI/Pages/GHCR topology |
| CICD-03 | Docker image publishes to GHCR on tag, zero build step to pull | Finding 5 (GHCR visibility), Finding 7 (QEMU + prebuilt wheels), Code Examples §release.yml |
</phase_requirements>

## Summary

Phase 23 is almost entirely a **mechanics** problem, not a design problem — CONTEXT.md has already made every judgment call. The work here closes the loose ends CONTEXT.md explicitly flagged as needing verification.

**The single most consequential finding:** `logs/dexter.log` does **not**, and structurally **cannot**, contain real Gemini-generated Dexter output. `services/gemini.py::chat()` logs only `len(response.text or '')` — the character count — never the text itself, at every call site across the whole codebase. This was confirmed by direct code inspection (not just an absent grep result), so it is stated as fact, not a hedge. **PORT-02 therefore has exactly one human-blocking dependency**: the user must supply a handful of real `/ask`/`/roast`/ambient-roast lines by pasting them from a live Discord session (screenshot, or copy-paste after next time the bot runs), which becomes the sole item in `23-HUMAN-UAT.md` for this requirement. This was anticipated by CONTEXT.md as the "if it does not" branch, and that branch is what actually happened.

The second most consequential finding is that **D-02's `dist/` scan is not merely "the load-bearing decision of the phase" rhetorically — it is genuinely a stronger guarantee than widening the original guard's extension allowlist would have been**, because it inspects the literal bytes shipped to the browser regardless of which templating layer produced them. It does discharge Phase 22's deferred IN-01 item for the concern that motivated it. There is one narrow, named residual risk (client-side-JS-constructed URLs would not be caught by a static-file scan) that does not apply to this phase's implementation (Astro ships zero JS by default per D-01, and the invite link is a static anchor per D-05), but is worth recording as a boundary of the guarantee, not glossed over.

Third: **D-12's "workflow_run vs needs:" framing in CONTEXT.md undersells how constrained the choice actually is.** `needs:` only creates dependencies between jobs *within the same workflow file*. Because D-03 locks the scan and the deploy into two separate files with different permission ceilings, `needs:` cannot express the gate at all — `workflow_run` triggered on `ci.yml`'s completion, filtered to `conclusion == 'success'` and `head_branch == 'main'`, with the deploy job explicitly checking out `github.event.workflow_run.head_sha` (not a bare `actions/checkout` default), is the only mechanism that satisfies D-03 and D-12 simultaneously.

Fourth: GHCR's multi-arch build (D-16) is **not** the QEMU horror story the phrase "multi-arch build under QEMU" usually implies for a compiled-language project. Every native-extension Python dependency in `requirements.txt` (`PyNaCl`, `davey`, `asyncpg`, `pgvector`) ships prebuilt `manylinux_aarch64` wheels for `cp311` — verified directly against PyPI's JSON API. `apt-get install ffmpeg` is a prebuilt-package install, not a compile. The QEMU tax here is "a few extra minutes downloading emulated wheels and running a package manager," matching D-16's own cost estimate, not a multi-hour compile ordeal.

Fifth: the D-13 push carries a real, verified-concrete red-CI risk, but it is narrower and cheaper than "some Phase 19-22 test will fail." Running `ruff check .` locally at HEAD passes clean; running `ruff format --check .` **fails on 3 files** (`cogs/events.py`, `tests/test_guild_config_logic.py`, `tests/test_memory.py`) with purely mechanical line-wrap differences — a one-command fix. **The full local pytest suite was run to completion this session: 1036 passed, 124 skipped, 0 failed, in ~7 minutes (417s).** The 124 skips are entirely the expected DB-unavailable skip pattern (no local Postgres running) — every test that could execute did, and none failed. This is strong, direct, complete evidence — not a sample — that the codebase itself is sound at HEAD; the only concretely-identified red-CI risk from local reproduction is the `ruff format` drift, which is trivially fixable before or as part of the push.

**Primary recommendation:** Sequence Phase 23 as (1) `ruff format .` + the 144-commit push, watch CI, fix whatever the real run surfaces (expect this to be close to a non-event given the clean local suite, but the ~111 DB-gated tests still deserve a real look against CI's actual `pgvector` container rather than assumed-identical); (2) Astro site scaffold + D-02 drift scan wired into `ci.yml`; (3) `pages.yml` gated via `workflow_run`; (4) GHCR `release.yml`; (5) README rewrite + landing page copy + Playwright GIF render, all after the plumbing is proven so the recruiter-facing artifacts are demonstrably live before they're described as such.

## Finding 1 — `logs/dexter.log` does NOT contain real Dexter AI output (PORT-02 / D-06)

**Checked first, as CONTEXT.md instructed. Answer: no, and here's the code-level proof, not just an absent grep.**

`services/gemini.py::chat()` (the single function behind `/ask`, `/roast`, ambient roasts, proactive callbacks, and the music-command roast) logs exactly this at every call:

```python
log.info(f"── Gemini chat request (priority={priority}) ──")
log.info(f"System prompt ({len(system_prompt)} chars):\n{system_prompt}")
log.info(f"Conversation ({len(conversation)} messages):")
#   [per-message] log.info(f"  [{i}] {msg['role']}: {msg['content'][:200]}")
log.info(f"Gemini chat response: {len(response.text or '')} chars")   # <-- length only, never response.text
return response.text if response.text else None
```

No file in `cogs/`, `services/`, or `logic/` logs `response.text` (or any slice of it) anywhere in the repository — verified by grepping every `log.info`/`log.debug` call site in `cogs/ai.py`, `cogs/events.py`, `cogs/music.py`, and `services/gemini.py`. A sample of what `logs/dexter.log` actually contains (grepped directly, verbatim):

```
[2026-07-14 00:06:41] [INFO] [dexter] ── Gemini chat request (priority=1) ──
[2026-07-14 00:06:41] [INFO] [dexter] System prompt (18 chars):
You are sarcastic.
[2026-07-14 00:06:41] [INFO] [dexter] Conversation (0 messages):
[2026-07-14 00:06:41] [INFO] [dexter] Gemini chat response: 19 chars
```

This entry (and the great majority of the log's content) is from the **pytest suite running against a mocked Gemini client** (`"You are sarcastic."` / `"test"` are literal test fixtures, not real system prompts — compare to the real `personality/prompts.py` system prompt, which is hundreds of characters) — not a live bot session at all. `logs/dexter.log` rotates daily and the current + all 10 retained rotated files were checked; none contain response text, because the code that would need to log it doesn't exist.

**Conclusion, stated plainly per CONTEXT.md's instruction not to hedge: the verbatim-real-output requirement CANNOT be satisfied from `logs/dexter.log`.** PORT-02 needs exactly the fallback CONTEXT.md already planned for: the user supplies a handful of real lines (a ~1-minute task — a screenshot or copy-paste from any past/future Discord session), recorded as the single `23-HUMAN-UAT.md` item for PORT-02. This is now a confirmed fact, not a risk.

**A secondary, structurally different source exists and is worth flagging to the planner, though it does not fully satisfy D-06 on its own:** `personality/responses.py` and `personality/roasts.py` contain the **hand-authored template fallback pools** — real, already-shipped, verbatim strings Dexter sends to Discord in production whenever Gemini is rate-limited or fails (e.g. `RATE_LIMIT_MESSAGES`, `AUTO_QUEUE_ANNOUNCE`, `VOICE_JOIN_ROASTS`). These are **not fabricated for the demo** — they are pre-existing, deployed, literal output strings, zero new authorship required. But they are template fallbacks, not Gemini generations, and D-06's stated concern is specifically about implying words are "Gemini's generation" when they aren't. Using them in the mock would be honest in the narrow sense of "real shipped Dexter text" but could misrepresent *provenance* the same way D-06 warns against — recommend the planner NOT substitute these for the human-sourced Gemini lines without an explicit user decision, since it reopens exactly the honesty question D-06 already resolved. Flagging as available but not recommended as a silent substitute.

## Finding 2 — Astro project-page subpath config (D-14, PORT-01)

**Verified via Context7 (official Astro docs, `withastro/docs`), HIGH confidence.**

For a GitHub Pages *project* page (not a user/org root page), `astro.config.mjs` needs both:

```js
// astro.config.mjs
import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://jadrianports.github.io',
  base: '/dexter',
});
```

`site` is the origin; `base` is the repo-name subpath. **Both are required** — `site` alone is not sufficient for correct asset/link resolution under a subpath. Getting `base` wrong (omitted, or without the leading slash) is the single most common Astro-on-GitHub-Pages failure — every asset reference, and every `<a href="/...">` written as an absolute root path, resolves to `jadrianports.github.io/foo` instead of `jadrianports.github.io/dexter/foo`, producing a page that works perfectly in local `astro dev` (served at `/`) and 404s on every asset the moment it's deployed. Astro's `astro:assets` and `Astro.url`-derived paths correctly prepend `base` automatically; **hand-written relative or root-absolute `href`/`src` attributes in `.astro`/`.html` markup do not** — they must either be written as relative paths (`./assets/x.png`) or explicitly prefixed with the `base` import from `astro:config/client`. This is the concrete failure mode to check for in review: any literal `/foo` string in the mock/hero/CTA markup.

**Official recommended CI/CD pattern (Context7, `withastro/docs`):** Astro ships an official composite action, `withastro/action@v6`, which wraps install + build + `upload-pages-artifact` in one step. This is the right fit for `pages.yml` (which wants build+upload+deploy). It is **not** the right fit for `ci.yml`'s scan job, because that job must build the site *without* uploading a Pages artifact (it has no `pages: write` permission per D-03) — the scan job should use plain `actions/setup-node` + `npm ci` + `npm run build`, giving full control over the `dist/` path the scan step reads, rather than a composite action whose primary purpose is the artifact upload this job must not perform.

**Node version / lockfile / repo hygiene (planner discretion, but concrete facts to plan against):**
- `npm ci` requires a **committed `package-lock.json`** — without it, `npm ci` fails outright (`npm ci` refuses to run without a lockfile, by design, unlike `npm install`).
- `.gitignore` already contains a bare `node_modules/`-shaped gap that must be closed — current `.gitignore` has no `node_modules/` entry at all (checked directly). Must be added before the first `npm install` in `/site`, or the entire dependency tree gets committed. Also add `site/dist/` for symmetry with the already-present bare `dist/` entry (which technically already matches `site/dist/` since the pattern has no leading `/`, but an explicit entry improves readability).
- `.dockerignore` does **not** currently exclude `site/` or `node_modules/` (checked directly, full current contents reviewed) — must be added so the Node toolchain and its `node_modules/` tree never enter the Docker image layer (the image only needs `requirements.txt`-installed Python + the bot source; `/site` is portfolio content with zero runtime relevance to the running bot).
- Recommend pinning Node **`"22"`** or newer LTS in `actions/setup-node` (Astro 6.x line — visible in the Context7 result set — targets recent Node; the exact minimum should be read from the `engines` field Astro's scaffolding writes into `package.json` when `npm create astro@latest` is run, rather than guessed here).

## Finding 3 — D-02 `dist/` drift scan: invocation shape, positive control, IN-01 discharge (PORT-01/03, CICD-02)

**Reusable assets from `tests/test_invite_drift_guard.py` (read in full):**
- `URL_PATTERN` — the regex matching all three embedding forms (Markdown link, HTML href, bare). Directly reusable, no changes needed.
- `_canonical_url()` — wraps `build_invite_url()` with the config constants. Directly reusable.
- `_collect_offenders(paths, canonical)` — takes an **explicit path list**, not an internally-derived one; this is exactly the seam the D-02 scan should plug into. It already returns `list[tuple[str, str]]` of `(file, drifted_url)`.
- The `PLANNING_PREFIX` exclusion and `TEXT_EXTENSIONS` allowlist are **not directly relevant** to the `dist/` scan (dist/ is not git-tracked at all, so `git ls-files`-based filtering doesn't apply — the scan needs a different file-collection function that walks the actual built directory, e.g. `Path(dist_dir).rglob("*.html")`).

**Why the extension-allowlist filtering doesn't matter here:** the original guard's blindness under Astro isn't really about `.astro` not being in `{.md, .html, .txt}` — it's that `dist/index.html` (which *would* match `.html`) is never git-tracked, so `git ls-files` never surfaces it regardless of extension. The fix is necessarily a **different collection strategy** (filesystem walk vs `git ls-files`), not an allowlist change. This is the correct read of D-02, and it's the reason a source-allowlist widening (the rejected alternative, "Rejected: widening the guard's allowlist to `.astro`") would not have worked at all — `.astro` source files contain component syntax and template expressions, not the final literal string; scanning them would either miss interpolated URLs entirely or require an Astro-template parser, neither of which the artifact scan needs.

**Recommended invocation shape:** a new test function using a `SITE_DIST_REQUIRED` environment variable to convert "dist absent" from a graceful skip (correct for local `pytest` with no Node build) into a hard failure (correct for CI, where the build step is mandatory and always runs first):

```python
# tests/test_site_drift_guard.py (new file — see extraction note below)
import os
from pathlib import Path
import pytest

from tests.test_invite_drift_guard import _canonical_url, _collect_offenders

SITE_DIST_DIR = Path("site/dist")

def _dist_html_files(dist_dir: Path) -> list[Path]:
    if not dist_dir.exists():
        return []
    return list(dist_dir.rglob("*.html"))

def test_no_drift_in_built_site():
    """D-02: guards the actual shipped artifact, not the .astro source.
    Set SITE_DIST_REQUIRED=1 in ci.yml's site job so this can never
    silently skip in CI — locally (no Node build run) it skips with a
    clear message instead."""
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


def test_dist_drift_guard_actually_detects_a_mismatch(tmp_path):
    """Mandatory positive control mirroring T-22-02a — required per
    CONTEXT.md D-02 discretion note and the Phase 22 D-10 precedent."""
    fake_html = tmp_path / "index.html"
    fake_html.write_text(
        '<a href="https://discord.com/oauth2/authorize?client_id=999&permissions=8&scope=bot">Add</a>',
        encoding="utf-8",
    )
    offenders = _collect_offenders([fake_html], _canonical_url())
    assert offenders, "dist/ scanner failed to catch a deliberately-wrong invite URL"
```

Then `ci.yml`'s new site job runs, in order: `npm ci` → `npm run build` (produces `site/dist/`) → `SITE_DIST_REQUIRED=1 pytest tests/test_site_drift_guard.py -v`. This satisfies "must fail the build on drift" (assert failure) and "must never silently skip in CI" (the env var converts the only skip path into a failure) in one mechanism, without inventing a new pytest plugin or CLI flag — `pytest --no-skip` does not exist; this environment-variable-gated skip/fail split is the real, standard way projects solve this (a documented pattern, not a novel invention — pytest's own docs describe `pytest.skip`/`pytest.fail` as the two outcomes, and gating between them on an env var is ordinary application code, not a pytest feature).

**Import-across-test-modules note:** `from tests.test_invite_drift_guard import _canonical_url, _collect_offenders` is valid but slightly unconventional pytest style, and only works if `tests/` has an `__init__.py` or pytest's rootdir/import-mode makes `tests` importable as a package (check current `pyproject.toml` `[tool.pytest.ini_options]` `testpaths`/import settings before committing to this). **Cleaner alternative, recommended if the import doesn't work cleanly:** extract `URL_PATTERN`, `_canonical_url`, `_collect_offenders` into a small non-test-collected helper module (e.g. `tests/_url_scan.py` — leading underscore keeps pytest from collecting it as a test module) that both `test_invite_drift_guard.py` and the new `test_site_drift_guard.py` import from. Either approach satisfies "reuse the regex, don't duplicate it" — the planner's call per CONTEXT.md discretion.

**IN-01 discharge assessment — honest, not just adopting CONTEXT.md's framing:** IN-01 was Phase 22's deferred concern that the original guard's `.md`/`.html`/`.txt` extension allowlist would miss a URL embedded in a new file type. D-02's artifact-level scan **does genuinely discharge this**, and it is a *stronger* guarantee than widening the allowlist would have been — it inspects the literal bytes shipped to the browser, so it's correct regardless of what templating language, string concatenation, or component nesting produced them, as long as the result is static text in the HTML output. **Named residual limitation (not hypothetical noise — a real boundary of the guarantee):** if a future Astro island or client-side script ever constructed the invite URL at runtime in the browser (rather than at build time in static markup), the artifact scan — which reads raw file bytes — would not see it, because the URL would never appear as a literal string in `dist/*.html`. This does not apply to the current implementation (D-01's zero-JS-by-default posture + D-05's plain `<a>`/button markup mean the URL is always static build-time text), so IN-01 is discharged **for this phase's actual shape**, with the residual documented rather than hidden.

## Finding 4 — Pages workflow topology, `workflow_run` gating (D-03, D-11, D-12, PORT-01, CICD-02)

**Verified: Context7 (Astro's official example, `withastro/docs`) for the base shape; GitHub API (`gh api repos/actions/.../releases/latest`) for exact current versions; WebSearch cross-referenced for `workflow_run` gotchas.**

**Current action versions (fetched directly from GitHub's releases API, HIGH confidence — most authoritative source available):**
| Action | Latest tag |
|---|---|
| `actions/checkout` | `v7` |
| `actions/setup-node` | `v7` |
| `actions/configure-pages` | `v6` |
| `actions/upload-pages-artifact` | `v5` |
| `actions/deploy-pages` | `v5` |
| `docker/setup-qemu-action` | `v4` |
| `docker/setup-buildx-action` | `v4` |
| `docker/login-action` | `v4` |
| `docker/metadata-action` | `v6` |
| `docker/build-push-action` | `v7` |

(Note: `ci.yml` currently pins `actions/checkout@v4` and `actions/setup-python@v5` — both behind current major releases. Not a Phase 23 blocker or in-scope requirement, but worth a one-line mention to the planner as a low-priority opportunistic bump, not gating.)

**Why the deploy cannot live in `ci.yml` (confirmed by reading the file):** `ci.yml`'s top-level block is `permissions: contents: read`, with an explicit comment stating this denies write even to the default `GITHUB_TOKEN`, and the file's header comment names `pull_request` (never `pull_request_target`) as deliberate, citing "T-18-CIPRIV" — running untrusted forked-PR code with an elevated token is exactly the risk that ceiling exists to prevent. `actions/deploy-pages` requires `pages: write` + `id-token: write` at the job level, which is structurally incompatible with that ceiling without either (a) widening `ci.yml`'s top-level permissions (a real regression the project has consistently avoided per its "structural safety over remembered safety" convention, cited by Phase 18/20), or (b) putting the elevated job behind an `if: github.ref == 'refs/heads/main'` guard inside `ci.yml` (rejected explicitly by CONTEXT.md D-03: "trusting nobody removes the guard").

**D-12's real constraint, more precise than CONTEXT.md's framing:** `needs:` creates a dependency *between jobs in the same workflow file*. It cannot express "job in `pages.yml` waits for a job in `ci.yml`" at all — that's not a permissions tradeoff, it's a hard GitHub Actions limitation. Given D-03 already locks the two concerns into separate files, `workflow_run` is not "the more complex of two options" — **it is the only mechanism available**, once D-03 is accepted. Recommend removing "the planner's call" framing when this ships and documenting it as forced, so a future reader doesn't wonder why the "simpler" `needs:` wasn't used.

**`workflow_run` footguns, and the concrete mitigation for each (WebSearch, cross-referenced against multiple independent reports):**
1. **Branch-filter behavior differs when the triggering workflow was itself triggered by a `workflow_run`** (a chained-`workflow_run` problem) — does not apply here, `ci.yml` is triggered by `push`/`pull_request` directly, not another `workflow_run`. Not a risk for this topology.
2. **`actions/checkout`'s default behavior checks out the ref of the workflow that's currently running (`pages.yml`'s own trigger context), not automatically the commit that triggered `ci.yml`.** The fix is to pass `ref: ${{ github.event.workflow_run.head_sha }}` explicitly to `actions/checkout` in `pages.yml` — never rely on the default checkout behavior for a `workflow_run`-triggered job.
3. **The artifact/checkout is NOT automatically the same commit** — `pages.yml` must rebuild from `head_sha`, it cannot reach into `ci.yml`'s already-built artifacts (different workflow runs don't share the build filesystem). This is exactly D-11's "accepted cost: the site builds twice" — confirmed as a real, unavoidable consequence of the `workflow_run` boundary, not an implementation inefficiency to optimize away.
4. **Filter on both `conclusion` and `head_branch`** — a `completed` event fires on failure too, and on any branch (PRs included), so the `if:` condition needs both checks or a red PR-branch CI run and a stale unrelated branch could each spuriously attempt (and immediately no-op or misfire) a Pages deploy.

**Recommended `pages.yml` skeleton:**

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
          ref: ${{ github.event.workflow_run.head_sha }}

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

**Repo-side manual setup (confirmed genuinely required, HIGH confidence — WebSearch corroborated by GitHub's own docs summary, and independently confirmed by reading `actions/configure-pages`'s own `action.yml` directly):** `Settings → Pages → Build and deployment → Source: GitHub Actions` must be set **by hand, once, before the first deploy**. `actions/configure-pages`'s `enablement: true` input *can* do this programmatically, but its own `action.yml` states this explicitly requires "a token other than `GITHUB_TOKEN`" (a PAT with `repo` scope, or a GitHub App with `administration:write` + `pages:write`) — the default `GITHUB_TOKEN` is not sufficient. Given this project's established zero-secrets-in-CI posture (the whole reason D-04 of Phase 22 committed the client ID publicly was to keep CI secret-free), introducing a PAT just to automate a one-time toggle is not worth the tradeoff. **Recommend treating this as a `23-HUMAN-UAT.md` item**, consistent with the D-17 GHCR-visibility precedent — same acknowledged-deferred pattern the project has used since Phase 11. Until this manual step happens, `pages.yml`'s `deploy-pages` step will fail outright (the `github-pages` environment doesn't exist yet) — this should be sequenced explicitly as a prerequisite to testing `pages.yml`, not discovered as a mystery failure.

## Finding 5 — GHCR multi-arch publish (D-16, D-17, CICD-03)

**Verified: GitHub API for exact versions (above); Docker's own official docs (WebFetch, `docs.docker.com/build/ci/github-actions/multi-platform/`) for the workflow shape; WebSearch cross-referenced for the visibility claim.**

**Recommended `release.yml` skeleton:**

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

`docker/metadata-action` lowercases image references automatically, but `ghcr.io/jadrianports/dexter` is already all-lowercase, so no special handling is needed here.

**QEMU / native-dependency risk assessment — this is the concrete answer to the "will this be brutal" question, verified directly against PyPI's JSON API (not assumed):**

| Package | `manylinux_..._aarch64` wheel for `cp311`? |
|---|---|
| `PyNaCl` 1.6.2 | Yes — `manylinux2014_aarch64` and newer manylinux tags |
| `davey` 0.1.6 | Yes — `manylinux_2_17_aarch64` |
| `asyncpg` 0.31.0 (the exact pinned version) | Yes — `manylinux2014_aarch64` |
| `pgvector` | Pure Python — architecture-independent, no wheel concern |

**Conclusion: none of the Dockerfile's native-extension Python dependencies require compilation under QEMU on `linux/arm64`.** `pip install` on the emulated arm64 leg downloads a prebuilt wheel exactly as it would on native arm64 hardware; the only work QEMU actually has to emulate is `apt-get install ffmpeg curl` (a `.deb` package install, not a compile — ffmpeg is available as a standard `bookworm` `arm64` package) and the interpreter/pip bookkeeping itself. This is consistent with — and now confirms with evidence — D-16's own cost estimate ("a few extra minutes on a rare event"), not the "brutal build time" the research prompt raised as a possibility. **Recommend the buildx+QEMU single-job approach over a per-arch matrix + manifest-merge** — the matrix approach exists specifically to dodge slow native compiles under emulation, which is not a real cost here.

**GHCR visibility (D-17) — confirmed genuinely impossible from the workflow (MEDIUM-HIGH confidence, WebSearch cross-referenced across three independent sources, all agreeing):** a package pushed via `GITHUB_TOKEN` inherits the **access permissions** of the linked repository but **not its visibility setting** — GHCR packages are private by default regardless of the source repo being public, and the visibility toggle exists only as a manual UI action on the package's own settings page (or via the REST API with a PAT that has `packages` admin scope — again in tension with the project's no-PAT posture). D-17's plan (flip by hand, verify with a logged-out `docker pull`) is correct and is the only viable path without introducing a new secret.

## Finding 6 — D-13 push contingency: concrete, verified local findings (D-13)

**`ruff check .`** — clean, all checks passed (verified by running locally against the exact working tree at HEAD).

**`ruff format --check .`** — **fails.** Three files need reformatting:
- `cogs/events.py`
- `tests/test_guild_config_logic.py`
- `tests/test_memory.py`

The diff for `cogs/events.py` (representative — checked directly) is purely mechanical line-wrapping (two `await`-call statements that fit on one line under the project's configured line length but were manually wrapped across three lines). This is a single `ruff format .` + commit away from green — **recommend folding this into the D-13 push task itself** (run `ruff format .`, review the diff is purely whitespace, commit alongside or immediately before the 144-commit push) rather than discovering it as the first red CI run of the phase.

**`pytest -q` (full suite) — completed, verified to a definitive result this session:**

```
1036 passed, 124 skipped, 2 warnings in 417.12s (0:06:57)
```

1160 tests were collected; 1036 executed and passed; 124 skipped (entirely the expected `tests/conftest.py::pool` fixture's DB-unavailable skip path — this dev machine has no local Postgres running, matching the module's own documented "skipped (connection error) when no Postgres is available" behavior). **Zero failures.** The two warnings are pre-existing, unrelated noise (a stdlib `audioop` deprecation notice from `discord.py`'s own import, and a benign `RuntimeWarning` about an unawaited mock coroutine inside one test's mock setup) — neither indicates a functional problem.

**What this does and doesn't prove:** this is strong, direct evidence that the ~1036 DB-independent tests (covering the vast majority of `logic/`, `personality/`, service-layer unit tests, and mocked-Discord cog tests) are genuinely green at HEAD, not just spot-checked. It does **not** prove the ~124 DB-gated tests pass against a *real* Postgres — those never got the chance to run here at all (they skipped, they didn't pass-vacuously or fail-silently; the skip is honest and expected on this machine). CI's `pgvector/pgvector:pg16` service container will actually execute all ~124 of those, for the first time against Phases 19-22's code, when the D-13 push lands. **Recommend the planner treat this as: "the non-DB majority of the suite is confirmed clean; the DB-gated minority is the one genuinely unverified-locally slice, and it happens to be exactly where Phase 21's memory-scoping surgery (the Phase 13 CR-01-adjacent subsystem) lives" — watch that slice specifically in the first real CI run.**

**Confirmed via `gh run list --repo jadrianports/dexter`:** 3 runs exist, matching CONTEXT.md's corrected D-13 narrative exactly — one `failure` (`docs(phase-18): complete phase execution`), then two `success` runs, the last being `docs(phase-18): evolve PROJECT.md after phase completion` at `2026-07-09T23:12:55Z`. `origin/main` is confirmed still parked there — `git rev-list --count origin/main..HEAD` currently reports **144** unpushed commits (CONTEXT.md said "143"; one additional context-gathering commit landed since). Pitfall-7's davey/PyNaCl warning in `ci.yml`'s comments is confirmed stale per CONTEXT.md's correction and should be removed as part of this phase's push-and-repair task, not left to imply a risk that already didn't materialize.

## Finding 7 — Playwright → GIF pipeline (D-06, D-07, PORT-02, PORT-03)

**Verified via Context7 (`websites/playwright_dev_python`, official docs) for the Playwright API; WebSearch for the ffmpeg conversion step.**

**Recommended pipeline — video capture, not screenshot-sequence assembly:** Playwright Python's `page.screenshot()` **disables CSS animations by default** unless explicitly told `animations="allow"`, making a screenshot-loop approach fight the tool rather than use it as intended. The correct, natively-supported mechanism is **browser context video recording**:

```python
# Source: Context7 /websites/playwright_dev_python (official docs, "Videos")
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(
        record_video_dir="scratch/videos/",
        record_video_size={"width": 900, "height": 560},
    )
    page = context.new_page()
    page.goto("file:///.../site/dist/index.html")   # or a local dev server URL
    page.wait_for_timeout(6000)   # let the CSS animation/scroll-reveal play out
    context.close()               # video only finalizes on close — must await/call this
    print(page.video.path())      # -> the recorded .webm
```

This records real, natural CSS-animation playback as a `.webm`, sidestepping the screenshot-animation-disabling default entirely. Convert with `ffmpeg` (already a project dependency, already in the Dockerfile — though note this conversion runs on a **dev machine, not in CI or the Docker image**, so it only needs to be locally available where the script is run):

```bash
# Source: ffmpeg two-pass palette approach (WebSearch, cross-referenced across
# multiple independent ffmpeg-GIF guides — standard, well-established technique)
ffmpeg -i demo.webm -vf "fps=12,scale=640:-1:flags=lanczos,palettegen=stats_mode=diff" palette.png
ffmpeg -i demo.webm -i palette.png -filter_complex \
  "fps=12,scale=640:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5" \
  docs/demo.gif
```

`palettegen`/`paletteuse` (a two-pass palette-optimized encode) is the standard technique for small-file, crisp-text GIFs — a naive single-pass GIF encode uses a fixed 256-color palette poorly suited to text-heavy UI content and produces visibly worse quality at a larger file size. `fps=12` and `scale=640` are reasonable starting points for the ~1-2MB target; tune both against the actual rendered output (exact values are planner/execution discretion per CONTEXT.md).

**Dependency placement (discretion, with a concrete recommendation and justification):** Playwright should **not** enter `requirements.txt` or `requirements-dev.txt`. Both are installed on every CI run (`requirements-dev.txt` currently holds only `ruff`, kept intentionally minimal) and `requirements.txt` is baked into the Docker image — Playwright plus its browser binary download (`playwright install chromium`, a ~150-300MB download) has zero runtime relevance to the running bot and zero relevance to any CI job (the GIF is not regenerated by CI — see below). Recommend a standalone `scripts/render_demo_gif.py` with a header comment documenting the one-time local setup (`pip install playwright && playwright install chromium`, run once by whoever regenerates the asset) and **treat the rendered `.gif`/`.webm` as a committed artifact, generated once, not a CI-produced build output** — explicit justification: (1) the demo content changes only when the mock's copy changes, which is rare relative to code changes; (2) adding a headless-browser dependency to CI trades away exactly the "fast, minimal-privilege, focused jobs" property D-03 is built around, for a job whose output is presentation content, not a build gate; (3) this matches the project's established pattern of committing generated-once assets (the avatar was set manually per prior-phase memory) rather than re-deriving them on every push.

## Finding 8 — README badges (D-15, PORT-03)

**Standard shields.io + GitHub Actions badge conventions (CITED: shields.io, a long-stable, widely-documented static-badge service — not independently re-verified against a live fetch this session, but the URL scheme is unchanged for years and is the same scheme already visible in thousands of public READMEs).**

```markdown
[![CI](https://github.com/jadrianports/dexter/actions/workflows/ci.yml/badge.svg)](https://github.com/jadrianports/dexter/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.3%2B-5865F2?logo=discord&logoColor=white)
![Postgres](https://img.shields.io/badge/postgres-pgvector-336791?logo=postgresql&logoColor=white)
![Gemini](https://img.shields.io/badge/gemini-2.5--flash-4285F4?logo=googlegemini&logoColor=white)
```

**The CI badge's exact URL form matters and is worth stating precisely:** `https://github.com/{owner}/{repo}/actions/workflows/{workflow-filename}.yml/badge.svg` — it must reference `ci.yml` by filename (not by the workflow's human-readable `name: CI` field, though the file's `name:` happens to also be `CI`), and the badge only renders a real status once at least one run of that exact workflow file has completed on the default branch — which is exactly why D-15 calls this badge "required" and ties it explicitly to D-13's push landing first. Before the push, this badge would render "no status" / a stale Phase-18-era result — do not screenshot or finalize README copy referencing "green CI" until after the D-13 push+repair sequence has actually gone green at HEAD.

## Architectural Responsibility Map

This phase does not fit the standard browser/SSR/API/CDN/DB five-tier model cleanly — it adds a static-site + CI/CD surface alongside the existing Discord-bot backend, not another tier of a web app. Mapped as closely as the taxonomy allows, with a sixth "Build/CI pipeline" row added for the concerns that don't correspond to any runtime tier at all:

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Landing page rendering (hero, features, boundaries, CTA) | CDN / Static | — | Astro SSG output served directly by GitHub Pages; zero server-side runtime, zero JS by design (D-01) |
| "Add to Discord" button | CDN / Static | External (Discord OAuth) | A static `<a href>` to `build_invite_url()`'s output; the actual OAuth flow is entirely Discord's own backend, outside this project |
| Demo mock (HTML/CSS Discord-conversation reproduction) | Browser / Client | — | Pure CSS animation/reveal, no server round-trip, no JS logic beyond optional `prefers-reduced-motion` handling |
| Invite-URL drift guard (`dist/*.html` scan) | Build/CI pipeline | — | Runs at build time inside `ci.yml`, never at runtime; guards the artifact before it ever reaches CDN/Static |
| Pages deploy | Build/CI pipeline | CDN / Static (target) | `pages.yml`'s job publishes the artifact; the Pages *serving* infrastructure itself is CDN/Static, entirely GitHub-managed |
| Docker image publish (GHCR) | Build/CI pipeline | Artifact Registry (GHCR) | Not a runtime tier at all — a supply-chain/distribution concern; the *bot* it packages is unchanged API/backend architecture, already shipped in prior phases |
| README case study | CDN / Static | — | Rendered by GitHub's own markdown pipeline; no build step, no runtime |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Astro | 6.x (per Context7's current doc corpus; confirm exact `npm create astro@latest` output at scaffold time) | Static site generator for `/site` | User-locked (D-01); ships zero JS by default, official first-class GitHub Pages support via `withastro/action` |
| Node.js | 22 (LTS) | Build runtime for the Astro toolchain in CI | Matches Astro 6.x's current baseline; pin explicitly in `actions/setup-node`, don't rely on the runner image default |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Playwright (Python) | latest at scaffold time | Records `.webm` video of the HTML/CSS mock for GIF derivation | **Dev-machine only, one-time/occasional run** — never CI, never `requirements.txt`/`requirements-dev.txt` (Finding 7) |
| ffmpeg | already installed (project dependency, in Dockerfile) | `.webm` → `.gif` conversion via palettegen/paletteuse | Same script/session as the Playwright capture; a dev-machine step, not CI |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `workflow_run` gating (Finding 4) | A single combined workflow with `needs:` | Not viable — `needs:` cannot cross workflow files; would also force merging the privileged Pages job into the unprivileged `ci.yml`, which D-03 explicitly forbids |
| Playwright video recording (Finding 7) | Screenshot-loop assembled into a GIF | Playwright's `page.screenshot()` disables animations by default, fighting the CSS-animation-driven mock; video recording captures natural playback with no special-casing |
| buildx + QEMU single job (Finding 5) | Per-arch native-runner matrix + `docker manifest create` merge | Matrix exists to avoid slow emulated compiles — moot here since every native dep has prebuilt aarch64 wheels (Finding 5); QEMU is simpler and D-16 already accepted its modest cost |

**Installation (site scaffold — planner/execution discretion on exact `npm create astro@latest` flags):**
```bash
cd site && npm create astro@latest . -- --template minimal --no-install --no-git
npm install
```

**Version verification:** Astro's exact pinned version should be recorded from the actual `npm create astro@latest` output at scaffold time (this research used Context7's live doc corpus, which reflects `astro_6.3.1` as of this session — training-data-independent, but still a snapshot; re-confirm at execution time with `npm view astro version`).

## Package Legitimacy Audit

**slopcheck was not run this session** (no packages are being `pip install`-ed by this phase — the only new runtime-adjacent dependency, Playwright, is explicitly recommended to live outside `requirements.txt`/`requirements-dev.txt` per Finding 7, as a dev-machine-only tool). Per the graceful-degradation protocol, packages named below are marked `[ASSUMED]` pending a `checkpoint:human-verify` gate at whichever plan actually runs `pip install`/`npm install`.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `astro` | npm | Years (multi-major, actively maintained) | Very high (millions/week class) | `github.com/withastro/astro` | not run | `[ASSUMED]` — well-known, but flag for a quick `npm view astro` sanity check at scaffold time |
| `playwright` | PyPI | Years, Microsoft-maintained | Very high | `github.com/microsoft/playwright-python` | not run | `[ASSUMED]` — dev-only, not shipped; lower risk given it never enters the Docker image or CI |

**Packages removed due to slopcheck [SLOP] verdict:** none — slopcheck was not run (no new `pip install` dependency in this phase's scope).
**Packages flagged as suspicious [SUS]:** none identified by inspection; both `astro` and `playwright` are widely-known, long-established projects with obvious, verifiable GitHub source repos — but the planner should still gate the first actual `npm install`/`pip install` behind a `checkpoint:human-verify` per the degradation protocol, since slopcheck genuinely did not run.

## Architecture Patterns

### System Architecture Diagram

```
                    ┌─────────────────────────────────────────────┐
                    │  Developer pushes to `main` (or opens a PR)  │
                    └───────────────────┬───────────────────────────┘
                                        │
                                        ▼
                    ┌─────────────────────────────────────────────┐
                    │  ci.yml  (permissions: contents: read)       │
                    │  — runs on EVERY push + PR —                 │
                    │                                               │
                    │  [existing] pytest + ruff job (unchanged)     │
                    │                                               │
                    │  [NEW] site job:                              │
                    │    checkout → setup-node → npm ci             │
                    │    → npm run build (site/dist/)                │
                    │    → SITE_DIST_REQUIRED=1 pytest               │
                    │       tests/test_site_drift_guard.py           │
                    │       (fails build on ANY drifted URL)         │
                    └───────────────────┬───────────────────────────┘
                                        │ completes (success/failure)
                                        ▼
                    ┌─────────────────────────────────────────────┐
                    │  pages.yml  (workflow_run: ["CI"], completed) │
                    │  permissions: pages: write, id-token: write   │
                    │                                               │
                    │  if: conclusion == 'success'                  │
                    │      && head_branch == 'main'                 │
                    │                                               │
                    │  checkout @ head_sha → rebuild site/dist/      │
                    │  → upload-pages-artifact → deploy-pages        │
                    └───────────────────┬───────────────────────────┘
                                        ▼
                          github.io/dexter (live landing page,
                          Add-to-Discord button → build_invite_url())

                    ┌─────────────────────────────────────────────┐
                    │  Developer pushes a `v*` tag                  │
                    └───────────────────┬───────────────────────────┘
                                        ▼
                    ┌─────────────────────────────────────────────┐
                    │  release.yml  (on: push: tags: ["v*"])        │
                    │  permissions: packages: write                 │
                    │                                               │
                    │  setup-qemu → setup-buildx → login(ghcr.io)   │
                    │  → metadata-action (tags: v*, latest)          │
                    │  → build-push-action                           │
                    │       platforms: linux/amd64,linux/arm64       │
                    └───────────────────┬───────────────────────────┘
                                        ▼
                    ghcr.io/jadrianports/dexter:v1.4.0 + :latest
                    (private until manual flip — 23-HUMAN-UAT.md)
```

### Recommended Project Structure
```
site/
├── astro.config.mjs        # site: 'https://jadrianports.github.io', base: '/dexter'
├── package.json
├── package-lock.json       # MUST be committed — npm ci requires it
├── src/
│   ├── pages/
│   │   └── index.astro     # single-scroll page (D-05): hero → demo → features → boundaries → CTA
│   ├── components/
│   │   ├── Hero.astro
│   │   ├── DemoMock.astro  # the HTML/CSS Discord-conversation reproduction (D-06)
│   │   ├── Features.astro
│   │   ├── Boundaries.astro  # PORT-04, positioned before CTA per D-05
│   │   └── Cta.astro
│   └── assets/              # images, if any — resolved correctly under `base` via astro:assets
└── dist/                    # git-ignored, CI/pages.yml-built only, never committed (D-11)

scripts/
└── render_demo_gif.py       # Playwright capture + ffmpeg conversion, dev-machine-only (Finding 7)

.github/workflows/
├── ci.yml                   # extended with the new site job (unprivileged)
├── pages.yml                # NEW — privileged Pages deploy
└── release.yml               # NEW — GHCR multi-arch publish (name per planner discretion)

docs/
└── demo.gif                  # committed artifact for README (D-07)
```

### Pattern: Single-source-of-truth invite URL reaching a static site with no server

`site/src/pages/index.astro` cannot import Python's `logic/invite.py` — it is a different language/runtime entirely. The pattern that preserves "one constructor" (D-03/D-07 of Phase 22) without a second hand-built URL: **the Astro build step reads the same public, committed constants** (`DISCORD_CLIENT_ID`, `INVITE_PERMISSIONS_VALUE`, `INVITE_SCOPES` — all already public per Phase 22 D-04) and reconstructs the identical query string using the *same literal values*, not a re-derivation of policy. Since `discord.utils.oauth_url()`'s output format is a well-known, stable Discord OAuth2 URL shape (`https://discord.com/oauth2/authorize?client_id=...&permissions=...&scope=...`), the Astro component can hardcode this shape as a template literal populated from a small `site/src/config.ts` (or inline frontmatter constant) that mirrors `config.py`'s three constants exactly. **This is the one place a "second URL constructor" is unavoidable** — it's a different language, there's no way to literally call `logic/invite.py` from Astro — but the D-02 `dist/*.html` scan is precisely the safety net that makes this acceptable: if the Astro-side constants ever drift from `config.py`'s, the CI scan fails loudly rather than the two silently diverging. Recommend the planner have `site/src/config.ts` constants carry a comment pointing back at `config.py`'s exact line numbers, so a future edit to one prompts a look at the other — belt-and-suspenders alongside the scan.

### Anti-Patterns to Avoid
- **Root-absolute `href`/`src` in `.astro` markup** (e.g. `href="/assets/foo.png"`) — resolves to `jadrianports.github.io/assets/foo.png` instead of `.../dexter/assets/foo.png` under the project-page `base`. Use relative paths or Astro's asset-import mechanism, which prepends `base` automatically (Finding 2).
- **Bolting the Pages-deploy job into `ci.yml` behind an `if:` branch guard** — explicitly rejected by D-03; a future PR could remove the guard and the elevated token would then run against untrusted PR code.
- **Regenerating the demo GIF in CI** — trades away `ci.yml`'s minimal-privilege, fast-job posture for presentation content that changes rarely (Finding 7).
- **Fabricating or "improving" the mock's Discord-conversation transcript text** — the entire honesty premise of D-06 collapses if any line isn't verbatim, sourced, real Dexter output (Finding 1).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pages artifact packaging + deployment | A custom `gh-pages` branch push script | `actions/upload-pages-artifact` + `actions/deploy-pages` | Explicitly rejected by D-11 already — official actions handle the OIDC token exchange, artifact format, and environment URL output correctly |
| Multi-arch Docker builds | Separate native runners per architecture + manual `docker manifest create` | `docker/setup-qemu-action` + `docker/setup-buildx-action` + `build-push-action` with `platforms:` | Standard, one-job pattern; Finding 5 confirms QEMU emulation cost is low for this specific dependency set, so the complexity of a matrix+merge approach buys nothing here |
| GIF quality/size tuning | A naive single-pass ffmpeg GIF encode, or a third-party screen-recording SaaS | ffmpeg two-pass `palettegen`/`paletteuse` | Already a project dependency; the palette-optimization step is the well-established fix for GIF quality-vs-size on text-heavy content |
| Invite-URL drift detection at the artifact level | A second Python function that re-derives/re-validates the URL structure | Reuse `_collect_offenders`/`URL_PATTERN`/`_canonical_url` from `tests/test_invite_drift_guard.py` (Finding 3) | The exact same comparison logic already exists, tested, and positive-control-proven; duplicating it risks the two guards silently drifting from each other |

**Key insight:** almost nothing in this phase should be hand-rolled — the entire CI/CD surface (Pages, multi-arch Docker) has a well-established, first-party GitHub/Docker Action for every step CONTEXT.md specifies. The one genuinely custom piece of code is the `dist/*.html` drift scan, and even that is >90% reuse of Phase 22's existing, tested scanning primitives.

## Common Pitfalls

### Pitfall 1: Astro `base` omitted or wrong — assets 404 only after deploy
**What goes wrong:** The page works perfectly under `astro dev` / `astro preview` locally (served at `/`), then every image, stylesheet, and root-absolute link 404s the moment it's live at `jadrianports.github.io/dexter`.
**Why it happens:** Local dev servers ignore `base` by default in some Astro versions/configurations, or a developer writes a literal `href="/foo"` instead of a relative path, bypassing Astro's automatic `base`-prefixing (which only applies to `astro:assets`-managed imports and Astro's own internal link helpers, not hand-written literal strings).
**How to avoid:** Set both `site` and `base` in `astro.config.mjs` from the start (Finding 2); never write a root-absolute `href`/`src` by hand in `.astro`/component markup; test with `astro preview` (which *does* honor `base`, unlike `astro dev` in some configurations) before the first real deploy.
**Warning signs:** Any hardcoded `/` -prefixed path in component markup during code review.

### Pitfall 2: `npm ci` fails in CI with no clear local repro
**What goes wrong:** `ci.yml`'s new site job fails at `npm ci` with an error about a missing or out-of-sync lockfile, while `npm install` works fine locally.
**Why it happens:** `package-lock.json` wasn't committed, or was regenerated locally without being re-committed after a `package.json` edit — `npm ci` is strict about lockfile/manifest sync in a way `npm install` is not.
**How to avoid:** Always commit `package-lock.json` alongside any `package.json` change; never `.gitignore` it (only `node_modules/` should be ignored).
**Warning signs:** `npm ci` succeeding locally but the CI job failing on a fresh checkout — usually means the lockfile in git is stale relative to a locally-modified `package.json`.

### Pitfall 3: The D-02 scan silently skips in CI, resurrecting the vacuous-pass hole
**What goes wrong:** The whole point of D-02 quietly stops being true — CI stays green forever even after the invite URL drifts, because the scan test skipped (dist/ wasn't where it expected, or the build step failed silently upstream) instead of failing.
**Why it happens:** A bare `pytest.skip()`-on-missing-dist pattern, copied without the `SITE_DIST_REQUIRED` env-var gate, behaves identically whether run locally (correct to skip) or in CI (must never skip).
**How to avoid:** The `SITE_DIST_REQUIRED=1` environment variable set only inside `ci.yml`'s site job step (Finding 3) — code review should specifically check this env var is present in the workflow YAML and that the test genuinely calls `pytest.fail()`, not `pytest.skip()`, when it's set.
**Warning signs:** A CI run whose site job passes in under a few seconds (too fast to have actually run `npm run build`) is a strong signal the scan skipped instead of running.

### Pitfall 4: `workflow_run` job never fires, or fires against the wrong commit
**What goes wrong:** Merging to `main` never triggers a Pages deploy at all, or deploys a landing page one commit behind what CI actually validated.
**Why it happens:** The `workflows:` array in `pages.yml`'s `workflow_run` trigger must match `ci.yml`'s `name:` field (`CI`) exactly, not the filename — a typo here causes the trigger to simply never fire, with no error anywhere. Separately, omitting `ref: ${{ github.event.workflow_run.head_sha }}` on `pages.yml`'s checkout step causes it to check out whatever `main` currently is at deploy time, which could differ from the exact commit `ci.yml` validated if another push landed in between.
**How to avoid:** Match the `name:` field exactly (Finding 4's skeleton uses `workflows: ["CI"]` matching `ci.yml`'s `name: CI`); always pass `head_sha` explicitly to checkout.
**Warning signs:** Pushing to `main` and the Pages deploy workflow never appearing in the Actions tab at all (trigger name mismatch) vs. appearing but publishing stale content (missing `head_sha`).

### Pitfall 5: First Pages deploy fails with an obscure environment error
**What goes wrong:** `actions/deploy-pages` fails on its very first invocation with an error referencing the `github-pages` environment not existing or not being configured for this deployment.
**Why it happens:** `Settings → Pages → Source` was never manually switched to "GitHub Actions" (Finding 4) — the environment GitHub auto-creates when that setting changes doesn't exist until it does.
**How to avoid:** Sequence the manual repo-settings step (documented as a `23-HUMAN-UAT.md` item) explicitly *before* attempting to validate `pages.yml`, not as an afterthought if the first run mysteriously fails.
**Warning signs:** A `pages.yml` run that fails immediately with an environment/configuration-related error rather than a build error.

### Pitfall 6: GHCR `docker pull` fails from outside the org even though the workflow "succeeded"
**What goes wrong:** `release.yml` reports green, the image is genuinely in GHCR, but `docker pull ghcr.io/jadrianports/dexter:v1.4.0` from a logged-out shell returns an authentication/not-found error.
**Why it happens:** GHCR packages are private by default regardless of the source repo's own visibility, and a `GITHUB_TOKEN`-based push does not carry visibility settings (Finding 5) — this is expected, not a bug in the workflow.
**How to avoid:** Treat the manual visibility flip as a required step, not optional polish — D-17 already frames this correctly; the pitfall is only in *not* expecting it and reading workflow-green as "done."
**Warning signs:** `docker pull` working fine for the repo owner (who has implicit access) while failing for anyone else — this is the exact symptom, and it's expected until the manual flip happens.

### Pitfall 7: `ruff format --check .` red on the very first post-push CI run
**What goes wrong:** The D-13 push's "watch the run" step immediately shows a lint-stage failure, unrelated to any actual Phase 19-22 logic bug, that could be mistaken for a more serious regression.
**Why it happens:** Confirmed directly this session (Finding 6) — three files (`cogs/events.py`, `tests/test_guild_config_logic.py`, `tests/test_memory.py`) have accumulated minor formatting drift relative to the pinned `ruff` version's current formatting rules.
**How to avoid:** Run `ruff format .` and commit the (purely whitespace) diff as part of or immediately before the D-13 push task, so this doesn't consume debugging time as if it were a real regression.
**Warning signs:** N/A — this is now a known, confirmed, pre-diagnosed finding, not something to detect.

## Code Examples

See Finding 3 (`test_site_drift_guard.py`), Finding 4 (`pages.yml`), Finding 5 (`release.yml`), and Finding 2 (`astro.config.mjs`) above — all sourced from Context7 (Astro official docs), the GitHub releases API (exact version numbers), and Docker's official multi-platform CI docs, reproduced in full there rather than duplicated here.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `actions/upload-artifact`/`download-artifact` v3 (for Pages) | v4-line `upload-pages-artifact`/`deploy-pages` (now on v5) | Jan 30 2025 deprecation of the v3 generic artifact actions | Any tutorial or training-data example referencing `actions/upload-pages-artifact@v3` or earlier is stale and will fail on current GitHub Actions runners |
| Manually assembling a GIF from a screenshot loop | Native browser video recording (`record_video_dir`) → ffmpeg conversion | Standing Playwright feature, but frequently missed in favor of screenshot-loop tutorials | Screenshot-loop approaches fight Playwright's animation-disabling screenshot default; video recording sidesteps the problem entirely (Finding 7) |
| Pushing built site output to a `gh-pages` branch | `actions/upload-pages-artifact` + `actions/deploy-pages` (OIDC-based, no branch) | Standard GitHub-recommended approach since Pages-via-Actions launched | D-11 already locks this in; noted here as the reason the "old" pattern (which still appears in older tutorials/training data) should not be used |

**Deprecated/outdated:**
- `actions/upload-artifact@v3` / `actions/download-artifact@v3` for Pages workflows — retired; use the `-pages-artifact` variants, currently `v5`.
- The `ci.yml` Pitfall-7 comment about davey/PyNaCl native-install risk — retired per D-13's correction (confirmed: `gh run list` shows a real successful run); recommend removing the comment as part of the D-13 push task rather than leaving a stale warning in the file.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Astro's exact current version is the `astro_6.3.1`-era doc corpus Context7 returned | Standard Stack | Low — `npm create astro@latest` at execution time will pull whatever is actually current regardless of this research's snapshot; re-verify with `npm view astro version` at scaffold time |
| A2 | shields.io's badge URL scheme (`img.shields.io/badge/...`) is unchanged | Finding 8 | Low — this scheme has been stable for years and is visible in thousands of live READMEs; not independently re-fetched this session |
| A3 | Recommended Node version `22` for `actions/setup-node` | Finding 2 / Standard Stack | Low-Medium — should be cross-checked against whatever `engines` field `npm create astro@latest` actually writes into `site/package.json` at scaffold time, rather than trusted blindly from this research |
| A4 | GHCR visibility-cannot-be-set-via-GITHUB_TOKEN claim, though corroborated by 3 independent WebSearch sources plus `configure-pages`'s own `action.yml` wording (a directly-fetched, first-party source) for the analogous Pages-enablement case | Finding 5 | Low — the Pages-side confirmation is HIGH confidence (fetched directly); the GHCR-specific claim is WebSearch-sourced and cross-referenced but not fetched from an official GitHub doc page directly this session |

**If this table is empty:** N/A — see rows above. All other claims in this research (log-content finding, ruff results, full local pytest result, PyPI wheel availability, exact action version tags, `workflow_run` file-boundary limitation, Pages manual-enablement requirement) were verified directly via tool calls (code inspection, `gh api`, `pip`/PyPI JSON API, `ruff`/`pytest` execution, Context7) this session and are not flagged as assumptions.

## Open Questions

1. **(RESOLVED) Does `logs/dexter.log` contain real Dexter AI output for the D-06 mock transcript?**
   - Resolution: No — confirmed by code inspection, not absence-of-evidence. `services/gemini.py` never logs response text, only its length, at every call site. PORT-02 needs a `23-HUMAN-UAT.md` item: user supplies real lines.

2. **(RESOLVED) Is `workflow_run` or `needs:` the right D-12 gating mechanism?**
   - Resolution: `workflow_run` is not a preference — it's the only mechanism available once D-03's file split is accepted, since `needs:` cannot cross workflow files.

3. **(RESOLVED) Does D-02's artifact scan genuinely discharge Phase 22's IN-01?**
   - Resolution: Yes, for this phase's actual implementation (zero-JS Astro, static anchor tags) — with one named, non-applicable-here residual limitation (client-side-JS-constructed URLs) documented rather than hidden.

4. **(RESOLVED) Will multi-arch GHCR builds be a QEMU compile-time problem?**
   - Resolution: No — every native-extension dependency (`PyNaCl`, `davey`, `asyncpg`) ships prebuilt `manylinux_aarch64` wheels for `cp311`, verified directly against PyPI. QEMU only has to emulate package-manager/wheel-download work, not compilation.

5. **(RESOLVED) Can `Settings → Pages → Source` be set automatically by a workflow?**
   - Resolution: No, not without a PAT/GitHub-App token this project's zero-secrets CI posture doesn't use. It's a one-time manual step, appropriately a `23-HUMAN-UAT.md` item, same pattern as D-17's GHCR flip.

6. **(RESOLVED, with one narrower residual) Is the full pytest suite actually green at HEAD (pre-push)?**
   - Resolution: The full local suite was run to completion this session — **1036 passed, 124 skipped, 0 failed** (417s). All 1160 collected tests were accounted for; the 124 skips are entirely the documented DB-unavailable fixture skip, not a suite gap.
   - Narrower residual: the 124 DB-gated tests never actually executed against a real Postgres locally (they skipped, correctly, given no local Postgres). CI's `pgvector` service container will be the first real execution of those tests against Phases 19-22's code — including Phase 21's memory-scoping surgery, the subsystem with the closest history to a real blocker (Phase 13 CR-01).
   - Recommendation: Treat the non-DB majority as confirmed green; watch the DB-gated slice specifically in the first real post-push CI run, per D-13's own "push, watch, fix" sequencing — this is now a narrow, named thing to watch, not an open unknown.

7. **(FOR THE PLANNER) Exact Astro version and Node minimum.**
   - What we know: Context7's current doc corpus reflects an `astro_6.3.1`-era snapshot; Node 22 is a reasonable current-LTS pin.
   - What's unclear: The exact versions `npm create astro@latest` will actually scaffold at execution time (this is inherently a moving target, not a research gap).
   - Recommendation: Re-confirm with `npm view astro version` at the scaffold task, and read the `engines` field Astro's own scaffolding writes into `package.json` rather than hardcoding a Node version from this research.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `gh` CLI (authenticated) | Verifying CI run history, checking action release versions | ✓ | 2.93.0, logged in as `jadrianports` with `repo`/`workflow` scopes | — |
| Node.js / npm | Astro site scaffold + build (local dev, and CI's site job) | Not checked on this dev machine this session — **verify before scaffolding** | — | If absent locally, scaffold/build can still be validated purely through CI once the workflow exists |
| Docker (local) | Not required for this phase — GHCR build runs entirely in CI | N/A | — | — |
| A local PostgreSQL instance | Full local `pytest` execution against DB-gated tests | ✗ (confirmed absent — 124 tests skip on this machine) | — | CI's `pgvector/pgvector:pg16` service container is the real substitute; not a blocker, D-13 already routes around this by design |
| ffmpeg | GIF conversion (dev-machine script) | ✓ (project dependency, used elsewhere in the bot) | — | — |

**Missing dependencies with no fallback:** none — every gap identified has a viable path (CI substitutes for local Postgres; Node/npm just needs local verification before the Astro scaffold task starts).
**Missing dependencies with fallback:** local Postgres (fallback: rely on CI's service container, consistent with D-13's own strategy).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (version per `requirements.txt`/`requirements-dev.txt` — not separately pinned; current environment resolved `pytest`/`pytest-asyncio` per existing `requirements.txt`) |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) — existing, unchanged by this phase except the new `tests/test_site_drift_guard.py` module |
| Quick run command | `pytest tests/test_site_drift_guard.py tests/test_invite_drift_guard.py -q` |
| Full suite command | `pytest -q` (confirmed this session: 1036 passed / 124 skipped / 0 failed / ~7min locally without DB; CI's `pgvector` container additionally exercises the 124) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PORT-01 | Landing page builds without error, deploys via Pages | integration (CI-only) | `cd site && npm run build` then inspect `pages.yml`'s run result | ❌ Wave 0 — `site/` doesn't exist yet |
| PORT-02 | Demo mock renders; transcript is verbatim (manual review, not automatable) | manual-only | N/A — code review that no line was authored fresh, cross-checked against the user-supplied `23-HUMAN-UAT.md` source lines | ❌ Wave 0 — mock component doesn't exist yet |
| PORT-03 | README case study present, badges render, mermaid renders on GitHub | manual-only (GitHub's own markdown rendering, not locally automatable) | N/A | ❌ Wave 0 — README rewrite pending |
| PORT-04 | Four boundaries present on both surfaces, wording matches PROJECT.md §Key Decisions | manual/code review | Grep landing-page + README source for boundary content, diff against PROJECT.md's shipped wording | ❌ Wave 0 |
| CICD-02 | Merge to main auto-deploys to Pages, gated on CI green | integration (CI-only, first real proof only after D-13 push + first `pages.yml` run) | Watch the Actions tab after a real merge to `main` | ❌ Wave 0 — `pages.yml` doesn't exist yet |
| CICD-03 | Tagged push publishes multi-arch GHCR image, pullable with zero build | integration (CI-only, first real proof only after tagging `v1.4.0`) | `docker pull ghcr.io/jadrianports/dexter:v1.4.0` from a logged-out shell (the `23-HUMAN-UAT.md` verification step, D-17) | ❌ Wave 0 — `release.yml` doesn't exist yet |
| (regression) | Invite URL drift never silently passes | automated, CI-required | `SITE_DIST_REQUIRED=1 pytest tests/test_site_drift_guard.py -v` | ❌ Wave 0 — new test file (Finding 3) |

### Sampling Rate
- **Per task commit:** `ruff check . && ruff format --check .` + the relevant narrow pytest slice (e.g. `tests/test_site_drift_guard.py` once it exists).
- **Per wave merge:** `pytest -q` (full local suite — confirmed this session to run in ~7 minutes without a local DB; faster against CI's containerized Postgres).
- **Phase gate:** Full suite green **in actual CI** (not just locally) before `/gsd-verify-work`, given this phase's entire premise is that the recruiter-facing artifacts are backed by a real, currently-green run — a locally-green suite that hasn't been proven in CI does not satisfy PORT-03's "CI badge reflects the actual last run" claim.

### Wave 0 Gaps
- [ ] `site/` — the entire Astro project does not exist yet (PORT-01, PORT-02).
- [ ] `tests/test_site_drift_guard.py` — the D-02 artifact-scan test (Finding 3) — covers the CICD-02/PORT-01 regression surface.
- [ ] `.github/workflows/pages.yml` — does not exist (CICD-02).
- [ ] `.github/workflows/release.yml` (or planner-chosen name) — does not exist (CICD-03).
- [ ] `README.md` rewrite — currently 2 lines (PORT-03).
- [ ] `scripts/render_demo_gif.py` — does not exist (PORT-02/PORT-03, D-07).
- [ ] `23-HUMAN-UAT.md` — does not exist yet; will carry the PORT-02 real-lines item, the Pages-Source-enablement item, and the D-17 GHCR-visibility-flip item.

*(No existing test infrastructure covers any of this phase's new surface — the entire Wave 0 list above is net-new, consistent with this being an almost entirely greenfield phase within an otherwise mature codebase.)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | This phase adds no auth surface — the landing page is static/public, the bot's existing auth (Discord OAuth) is unchanged and out of scope (Phase 22 already shipped it) |
| V3 Session Management | No | No sessions introduced |
| V4 Access Control | Yes (CI/CD supply-chain sense, not app-level) | Workflow `permissions:` blocks are the access-control surface here — least-privilege per job, matching the existing `ci.yml` posture (Finding 4) |
| V5 Input Validation | Marginal | The only "input" is the drift scan's regex over build output — already validated by Phase 22's positive-control discipline (Finding 3) |
| V6 Cryptography | No | No new cryptographic surface |

### Known Threat Patterns for GitHub Actions CI/CD + static-site publishing

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Untrusted PR code running with an elevated `GITHUB_TOKEN` (`pull_request_target` misuse) | Elevation of Privilege | Already the project's standing posture (`ci.yml` uses `pull_request`, never `_target`, T-18-CIPRIV) — this phase must not introduce a `pull_request_target` trigger anywhere, including `pages.yml`/`release.yml` (neither should be PR-triggered at all per D-03/D-16, which independently avoids this) |
| Privileged deploy job triggered by, or reachable from, a fork's workflow run | Elevation of Privilege | `workflow_run` events triggered by a workflow that itself ran on a fork do carry some historical GitHub Actions footguns; mitigated here because `ci.yml` only meaningfully triggers the Pages deploy path when `head_branch == 'main'` (Finding 4's `if:` condition), and forks cannot push to `main` |
| `GITHUB_TOKEN` over-scoped at the top of a workflow | Elevation of Privilege | Both new workflows declare their own minimal `permissions:` block (`pages: write`+`id-token: write` for `pages.yml`; `packages: write` for `release.yml`) rather than inheriting a broad default — matches `ci.yml`'s existing per-workflow minimal-permissions convention |
| Supply-chain compromise via an unpinned or `@main`-tracking third-party Action | Tampering | All recommended Actions are pinned to a specific major-version tag (`@v7`, `@v5`, etc. — Finding 4/5's version tables), matching `ci.yml`'s existing `@v4`/`@v5` pinning convention. (Pinning to a full commit SHA is a stronger control some projects use; this project's existing convention is major-tag pinning, and this research does not recommend deviating from established project convention without a separate discussion) |
| A malicious/compromised npm dependency in the new Node toolchain reaching the Docker image or the bot's runtime | Tampering | Addressed structurally: `.dockerignore` must exclude `site/`/`node_modules/` (Finding 2) so the Node dependency tree never enters the image that runs the bot; the npm surface is confined to the CI build environment for a static site, with no code execution at runtime |
| Invite-URL drift silently shipping a wrong (e.g. over-privileged) OAuth2 URL to the public | Tampering / Repudiation | The entire D-02/Finding-3 mechanism exists specifically to close this — a CI-enforced, positive-control-proven scan of the actual shipped artifact |

## Sources

### Primary (HIGH confidence)
- Context7 `/withastro/docs` — Astro's official GitHub Pages deployment guide (`site`/`base` config, official `withastro/action` workflow shape)
- Context7 `/websites/playwright_dev_python` — official Playwright Python docs on `record_video_dir`/video recording
- GitHub REST API (`gh api repos/{org}/{repo}/releases/latest`) — exact current major-version tags for `actions/checkout`, `actions/setup-node`, `actions/setup-python`, `actions/configure-pages`, `actions/upload-pages-artifact`, `actions/deploy-pages`, `docker/setup-qemu-action`, `docker/setup-buildx-action`, `docker/login-action`, `docker/metadata-action`, `docker/build-push-action`
- `actions/configure-pages`'s own `action.yml` (fetched directly via `gh api repos/actions/configure-pages/contents/action.yml`) — the `enablement` input's token-requirement wording
- PyPI JSON API (`pypi.org/pypi/{package}/json`) — direct wheel-availability check for `PyNaCl`, `davey`, `asyncpg` across manylinux aarch64 targets
- `gh run list --repo jadrianports/dexter` — actual CI run history (3 runs, corrects/confirms CONTEXT.md's D-13 narrative)
- Direct code inspection: `services/gemini.py`, `cogs/ai.py`, `cogs/events.py`, `cogs/music.py`, `personality/responses.py`, `personality/roasts.py`, `logic/invite.py`, `tests/test_invite_drift_guard.py`, `.github/workflows/ci.yml`, `Dockerfile`, `config.py`, `.gitignore`, `.dockerignore`, `requirements.txt`, `requirements-dev.txt`
- Direct local tool execution this session: `ruff check .`, `ruff format --check .`, `pytest -q` (full suite, completed to 1036 passed/124 skipped/0 failed), `git rev-list --count origin/main..HEAD`

### Secondary (MEDIUM confidence)
- Docker's official docs (WebFetch, `docs.docker.com/build/ci/github-actions/multi-platform/`) — multi-platform build workflow shape, cross-referenced against the directly-fetched action version numbers
- WebSearch, cross-referenced across 3+ independent sources — `workflow_run` gotchas (branch-filter chaining, checkout-ref defaults), GHCR default-private-visibility behavior, GitHub Pages manual-enablement requirement

### Tertiary (LOW confidence)
- shields.io badge URL scheme — not independently re-fetched this session; relied on well-established, long-stable convention (flagged in Assumptions Log A2)

## Metadata

**Confidence breakdown:**
- Standard stack (Astro, Playwright, ffmpeg): HIGH — Context7-verified official patterns, PyPI-verified wheel availability
- Architecture (workflow topology, `workflow_run` gating, permission boundaries): HIGH — directly confirmed by reading `ci.yml`, cross-referenced against GitHub's own action source (`configure-pages`'s `action.yml`) and Docker's official docs
- Pitfalls: HIGH for the CI/CD mechanics pitfalls (directly sourced or reproduced this session — e.g. the `ruff format` finding is a literal local repro, not inference); MEDIUM for the Astro `base`-path pitfall (well-documented pattern, not independently reproduced against a live deploy this session since `site/` doesn't exist yet)
- The PORT-02 log-content finding: HIGH — code-level proof, not inference, of a negative claim

**Research date:** 2026-07-14
**Valid until:** ~14 days for the version-numbers table (GitHub Actions ecosystem moves; re-verify tags at execution time via `gh api` if this research is more than 2 weeks stale) — the mechanics findings (log content, workflow_run file-boundary limits, GHCR visibility, wheel availability) are structural facts unlikely to change on that timescale.
