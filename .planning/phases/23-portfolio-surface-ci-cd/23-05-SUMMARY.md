---
phase: 23-portfolio-surface-ci-cd
plan: 05
subsystem: ui
tags: [astro, css-custom-properties, jetbrains-mono, accessibility, discord-invite]

requires:
  - phase: 23-03
    provides: Astro project scaffold at /dexter subpath, config.ts INVITE_URL, minimal Layout.astro placeholder, the built-artifact drift guard (test_site_drift_guard.py)
  - phase: 23-04
    provides: CI site-build + drift-scan job, Pages/GHCR workflows (unaffected by this plan's changes)
provides:
  - "site/src/styles/global.css — the single :root design-token declaration, self-hosted JetBrains Mono @font-face, .sr-only utility, reset, section background alternation, global prefers-reduced-motion floor"
  - "Self-hosted, Latin-subset JetBrains Mono 400/600 woff2 files (~15.15KB combined)"
  - "Completed site/src/layouts/Layout.astro: head (meta/OG/favicon/font preload), skip link, <main id=\"main-content\">, subpath-safe asset paths"
  - "Hero.astro, Cta.astro, Footer.astro — the two live invite-carrying surfaces + footer, verbatim UI-SPEC copy"
  - "index.astro rewired to compose Layout > Hero > Cta > Footer (deviation — see below)"
affects: [23-06]

tech-stack:
  added: []
  patterns:
    - "Design tokens as CSS custom properties in :root, referenced everywhere — zero bespoke hex/size values in components"
    - "Shared cross-component primitives (.cta-button, .h2-glyph) declared in global.css rather than component-scoped <style>, because set:html-injected raw HTML bypasses Astro's style-scoping attribute entirely"
    - "Font preload URLs sourced via ESM import (not a hand-typed literal path) so the preloaded URL is guaranteed byte-identical to the one @font-face actually fetches"

key-files:
  created:
    - site/src/styles/global.css
    - site/src/assets/fonts/jetbrains-mono-400.woff2
    - site/src/assets/fonts/jetbrains-mono-600.woff2
    - site/src/assets/fonts/OFL.txt
    - site/src/components/Hero.astro
    - site/src/components/Cta.astro
    - site/src/components/Footer.astro
  modified:
    - site/src/layouts/Layout.astro
    - site/src/pages/index.astro

key-decisions:
  - "Fetched JetBrains Mono v2.304 from the official GitHub release (OFL-1.1) and subset to Latin-1 + typographic punctuation + arrow glyphs via pyftsubset (a one-time dev-machine tool, confirmed absent from requirements.txt/requirements-dev.txt) to hit ~15KB combined, well under the 45KB budget."
  - "No box-shadow CSS declaration exists anywhere in global.css, not even `box-shadow: none` — the plan's own build-time verify regex (`/box-shadow\\s*:\\s*(?!none)/`) backtracks around a bare `none` value and false-flags it; omitting the declaration entirely satisfies both the regex and a plain grep cleanly."
  - "index.astro rewired to compose Hero/Cta/Footer (not in the plan's files_modified list) — necessary so the task's own dist/index.html verification (canonical URL x2, one h1, zero button) has real content to scan instead of 23-03's placeholder Fragment."

requirements-completed: []

duration: 25min
completed: 2026-07-14
---

# Phase 23 Plan 05: Global Stylesheet, Document Shell, Hero/CTA/Footer Summary

**The landing page's chassis is live: a token-driven dark/mono stylesheet, a subpath-safe document shell with a working skip link, and both "add to discord" buttons rendering the byte-identical canonical invite URL twice in the built page.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 3
- **Files modified:** 9 (3 created components + global.css + 3 font/license assets + Layout.astro + index.astro)

## Accomplishments

- Declared every UI-SPEC design token (7 colors, 7 spacing steps, 2 radii, 4 type sizes, 2 weights) once in `:root`, backed by a self-hosted, Latin-subset JetBrains Mono at ~15.15KB total — a third of the 45KB budget.
- Completed `Layout.astro`: correct `lang="en"`, OG tags, favicon + font preloads all subpath-safe, and a working skip-to-content link as the first focusable element.
- Built `Hero.astro` and `Cta.astro`, both importing `INVITE_URL` from `config.ts` and rendering the canonical Discord OAuth2 URL via the `set:html` escaping workaround — verified byte-identical, appearing exactly twice in `site/dist/index.html`.
- Wired `Footer.astro` and composed all four components into `index.astro`, giving the drift guard, the h1-count check, and the button-count check real content to scan.

## Task Commits

1. **Task 1: global.css — token layer, self-hosted font, reduced-motion floor** - `f582976` (feat)
2. **Task 2: Layout.astro — document shell, skip link, a11y floor** - `d3b8a01` (feat)
3. **Task 3: Hero, Cta, Footer — the two invite surfaces + voice** - `a0f7220` (feat)

_No plan-metadata commit issued yet — this summary + STATE/ROADMAP sync commit follows separately per protocol._

## Files Created/Modified

- `site/src/styles/global.css` — the single `:root` token source, `@font-face`, `.sr-only`, reset, section alternation classes, global reduced-motion floor, shared `.cta-button`/`.h2-glyph` primitives
- `site/src/assets/fonts/jetbrains-mono-400.woff2` (7676 B), `jetbrains-mono-600.woff2` (7840 B) — self-hosted, OFL-1.1, Latin-subset
- `site/src/assets/fonts/OFL.txt` — the JetBrains Mono license text, carried alongside the redistributed binaries (not in the plan's file list; added per OFL redistribution practice, harmless additive documentation)
- `site/src/layouts/Layout.astro` — completed head/body shell, skip link, subpath-safe asset references
- `site/src/components/Hero.astro` — h1, subhead, CTA #1, scroll-to-demo link, reduced-motion-aware blinking cursor
- `site/src/components/Cta.astro` — closing h2 with accent `>` glyph, body line, CTA #2, browse-the-code link
- `site/src/components/Footer.astro` — the one footer line
- `site/src/pages/index.astro` — composes `Layout > Hero > Cta > Footer` (deviation, see below)

## Decisions Made

- **Font sourcing:** fetched JetBrains Mono v2.304 directly from `github.com/JetBrains/JetBrainsMono`'s release ZIP (OFL-1.1, freely redistributable), then subset both weights (400, 600) to Latin-1 + typographic quotes/dashes/ellipsis + the arrow glyphs used in the page's own copy (`↓ ↗ →` code points), using `pyftsubset` from the `fonttools` package. `fonttools`/`brotli` were used as one-time local tools only — confirmed absent from `requirements.txt` and `requirements-dev.txt` (`grep -c fonttools requirements*.txt` returns 0), per the plan's T-23-SC mitigation. Combined payload: **15,516 bytes (~15.15 KB)**, well under the 45KB budget (no overage to disclose).
- **No `box-shadow` declaration anywhere, not even `box-shadow: none`:** the task's own build-time verify script uses the regex `/box-shadow\s*:\s*(?!none)/`, which — due to regex backtracking around the zero-width `\s*` — actually matches `box-shadow: none;` (the engine backtracks `\s*` to consume zero characters, positions the negative lookahead right before the space, and the lookahead trivially succeeds since the character there isn't literally `n`). Rather than fight the script's own quirk, the cleanest fix satisfying both the script and a plain `grep -c box-shadow` is to never write the property at all — nothing on this page uses shadows, so there is nothing to reset.
- **`index.astro` rewired (deviation, Rule 3 — blocking issue):** not in the plan's `files_modified` frontmatter, but Task 3's own verification (`grep -cF` the canonical URL in `dist/index.html`, `grep -c '<button'` → 0, "exactly one `<h1>`") is unsatisfiable while `index.astro` still renders 23-03's placeholder `Fragment set:html` pair instead of the real `Hero`/`Cta` components. Composed `Layout > Hero > Cta > Footer`, leaving a comment marking where `DemoMock`/`Features`/`Boundaries` land in plan 23-06.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Wired Hero/Cta/Footer into index.astro**
- **Found during:** Task 3 (Hero, Cta, Footer)
- **Issue:** The plan's `files_modified` list omits `site/src/pages/index.astro`, but that file still held plan 23-03's placeholder content (`<Fragment set:html={ctaHtml} />` twice around a "Real content lands in plans 23-05/23-06" paragraph). Task 3's acceptance criteria and automated verify step both scan the *built* `dist/index.html` for the real components' output (canonical URL count, `<h1>` count, copy verbatim match) — impossible to satisfy without composing the real components.
- **Fix:** Rewrote `index.astro` to import and render `Hero`, `Cta`, and `Footer` in place of the placeholder, with a comment noting Demo/Features/Boundaries are plan 23-06's scope.
- **Files modified:** `site/src/pages/index.astro`
- **Verification:** `npm run build` + all Task 3 grep/pytest checks pass against the real rendered output.
- **Committed in:** `a0f7220` (Task 3 commit)

**2. [Rule 1 - Bug] Fixed a whitespace-collapse bug around an inline `<code>` element**
- **Found during:** Task 3 (Cta.astro authoring)
- **Issue:** The initial `Cta.astro` body paragraph broke "dexter joins, waits for" and `<code>/setup</code>` across a line boundary inside the `<p>`. Astro's compiler stripped that boundary whitespace with no replacement space, rendering `waits for<code>/setup</code>` — no space between "for" and "/setup" in the actual shipped HTML.
- **Fix:** Collapsed the paragraph to a single line in the source so there is no cross-tag-boundary whitespace to rely on.
- **Files modified:** `site/src/components/Cta.astro`
- **Verification:** Rebuilt and grepped `dist/index.html` for `waits for <code...>/setup</code>` — confirmed a literal space now present.
- **Committed in:** `a0f7220` (Task 3 commit, folded into the same file's authoring — not a separate commit since it predates the task's first commit)

**3. [Rule 2 - Missing Critical] Carried the JetBrains Mono OFL license text alongside the redistributed binaries**
- **Found during:** Task 1 (font sourcing)
- **Issue:** The plan's file list covers only the two `.woff2` files; redistributing an OFL-licensed binary without its license text is a compliance gap, however minor.
- **Fix:** Copied `OFL.txt` from the release archive into `site/src/assets/fonts/` alongside the two subset weights.
- **Files modified:** `site/src/assets/fonts/OFL.txt` (new)
- **Verification:** File present, unmodified from the upstream release.
- **Committed in:** `f582976` (Task 1 commit)

---

**Total deviations:** 3 auto-fixed (1 blocking, 1 bug, 1 missing-critical)
**Impact on plan:** All three were necessary for the task's own stated verification to hold or for basic license compliance. No scope creep — Demo/Features/Boundaries remain untouched, deferred to plan 23-06 as instructed.

## Issues Encountered

- The unsubsetted JetBrains Mono webfonts (as shipped in the official release) are ~92KB/94KB each — more than 4x the 45KB combined budget. Resolved via Latin-subsetting per the plan's own contingency instructions; no user action needed.
- The plan's Task 1 verify script's box-shadow regex has a backtracking quirk that would false-flag a literal `box-shadow: none` reset rule. Resolved by never declaring the property (see Decisions Made).

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- The chassis (tokens, shell, both invite CTAs, footer) is complete and byte-verified against `build_invite_url()`'s canonical output via `tests/test_site_drift_guard.py`.
- `global.css`'s tokens, `.section`/`.section--dominant`/`.section--secondary` classes, `.sr-only`, and the `.h2-glyph`/`.cta-button` shared primitives are ready for plan 23-06's `DemoMock`, `Features`, and `Boundaries` components to consume directly — no new tokens should be needed there.
- **PORT-01 is NOT marked complete** — per this plan's instructions, PORT-01 only closes once the full page (hero + feature showcase + boundaries) exists, which is plan 23-06's scope.
- No blockers identified for 23-06.

## Self-Check: PASSED

All 7 created/modified source files and this SUMMARY.md verified present on disk; all 3 task commit hashes (`f582976`, `d3b8a01`, `a0f7220`) verified present in `git log`.

---
*Phase: 23-portfolio-surface-ci-cd*
*Completed: 2026-07-14*
