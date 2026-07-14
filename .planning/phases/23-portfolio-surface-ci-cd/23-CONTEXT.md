# Phase 23: Portfolio Surface & CI/CD - Context

**Gathered:** 2026-07-14
**Status:** Ready for planning

> **Session note:** All four gray areas were **explicitly selected by the user**, and every decision
> below is the user's **affirmative choice** — not an AFK adoption. Two decisions (**D-01 Astro**,
> **D-06 the HTML/CSS mock demo**) are the user **overriding Claude's stated recommendation**; both
> overrides were argued through and their real costs are recorded here, not papered over. Numeric and
> structural minutiae remain planner discretion per the Phase 11–22 precedent.
>
> This is the **last phase of v1.4** and the only recruiter-facing one. It is also the phase that
> forces the **140-commit push** (D-13) — every CI/CD deliverable here is unverifiable until GitHub
> has actually seen the repo.

<domain>
## Phase Boundary

Phase 23 ships the **recruiter-facing surface**: a static landing page, a README rewritten as an
architecture case study, honest scope disclosure, and the CD legs that publish both. It adds **zero
new production hosting** — the 24/7 deploy stays parked.

**Delivers exactly six requirements:**
- **PORT-01** — a static landing page in `/site` (hero, feature showcase, "Add to Discord" button).
- **PORT-02** — a short demo showing the personality landing, embedded in the landing page.
  **Deliberately reinterpreted** — see D-06.
- **PORT-03** — the README rewritten as an architecture case study (tagline, feature list,
  tech-stack badges, architecture summary, working invite link, CI badge).
- **PORT-04** — the four scope boundaries disclosed honestly: the 100-guild verification wall, the
  on-demand hosting caveat, the full-savage-personality + reactive-kill-switch tradeoff, and the
  hybrid memory scoping Phase 21 actually shipped.
- **CICD-02** — `/site` auto-deploys to GitHub Pages on merge to `main`.
- **CICD-03** — the Docker image publishes to GHCR on tag, pullable with zero build step.

**Not in this phase:**
- **Any prod auto-deploy of the bot.** There is no prod host this milestone (REQUIREMENTS.md
  §Out of Scope). CICD-03 makes a future host a `docker pull` away; it does not create one.
- **A second invite-URL constructor, a shortener, or a vanity redirect** — forbidden by Phase 22
  D-07. This phase *consumes* `logic/invite.py::build_invite_url()` and nothing else.
- Custom domain / DNS (D-14: default `github.io` path).
- A `LICENSE` file (implied by a license badge — deliberately not added, see D-15).

</domain>

<decisions>
## Implementation Decisions

### Landing page shape (PORT-01)

- **D-01 (user-selected, OVERRIDING Claude's recommendation): the landing page is an
  Astro static site in `/site`.** Claude recommended hand-rolled HTML/CSS (zero build step, zero new
  toolchain in a Python repo); the user chose an SSG. Astro specifically, because it **ships zero JS
  by default** — so `dist/` is essentially the static HTML we'd have hand-written anyway, which keeps
  the D-02 drift scan simple and the Pages artifact small — plus strong asset handling and
  HTML-shaped `.astro` components.
  **Accepted costs, recorded so nobody rediscovers them at execution time:** a Node toolchain
  (`package.json`, `node_modules`, `npm ci`) enters a Python-only repo; the Pages workflow gains a
  build step; and the SSG **breaks the Phase 22 drift guard by construction** unless D-02 is
  implemented.
  *(Rejected: single-file inline HTML — unreviewable diffs. Rejected: 11ty — lighter, but weaker
  asset pipeline and less familiar templates for a portfolio repo's readers.)*

- **D-02 (user-selected): the drift guard is preserved by BUILDING THE SITE IN CI AND SCANNING
  `dist/*.html`.** This is the load-bearing decision of the whole phase.
  **The problem it solves:** Phase 22's `tests/test_invite_drift_guard.py` is a *static text scan*
  over git-tracked files with a `.md`/`.html`/`.txt` extension allowlist. Under a hand-rolled site,
  `site/index.html` is tracked and covered for free. Under Astro, the committed source is `.astro`
  (not in the allowlist) and the rendered `dist/index.html` is **built in CI and never committed** —
  so the guard would scan nothing, **pass vacuously forever**, and SC-3's "drift is structurally
  impossible" would silently revert to being a comment. That is precisely the guarantee Phase 22
  spent a whole plan buying.
  **The fix:** a CI step runs the Astro build, then scans `dist/*.html` and asserts every
  `discord.com/oauth2/authorize…` URL it finds equals `build_invite_url()`'s output. This guards the
  **exact artifact shipped to Pages**, regardless of how the template produces the URL (literal,
  JS variable, or concatenation — all covered).
  **Accepted cost:** the check is **CI-only**. It cannot run in a plain local `pytest` because it
  needs a Node build first. The planner must decide how it is invoked (a pytest that shells out and
  skips when `dist/` is absent, vs a standalone script step) — but it **must fail the build** when
  it drifts, and it **must not silently skip in CI**.
  **This also closes Phase 22's deferred code-review item IN-01** (the drift guard's
  `.md`/`.html`/`.txt` extension allowlist), which the user explicitly deferred **to Phase 23** at
  Phase 22's close. D-02 is its resolution: rather than widening the allowlist to cover new source
  types, the guard gains a second, artifact-level check over the built output. The planner should
  confirm IN-01 is genuinely discharged by this and not merely bypassed.
  *(Rejected: widening the guard's allowlist to `.astro` — only guards a LITERAL string; the moment
  a template builds the URL from a variable the regex matches nothing and the guard goes blind while
  still reporting green. Rejected: a committed generated `invite-url.txt` as single source — Claude's
  recommendation, cheapest and keeps the gate inside plain pytest, but the user chose to guard the
  shipped artifact directly.)*

- **D-03 (locked topology): the drift SCAN lives in `ci.yml`; the Pages DEPLOY lives in its own
  `pages.yml`.** They need opposite permission levels and opposite triggers:
  - **Scan → `ci.yml`.** It is a *gate*: read-only, must run on **every push AND every PR**, must
    block a merge that would publish a drifted link. Needs no new permissions — the existing
    top-level `permissions: contents: read` ceiling suffices.
  - **Deploy → `pages.yml`.** It is *privileged*: `actions/deploy-pages` requires `pages: write` +
    `id-token: write`, which is exactly what `ci.yml`'s least-privilege ceiling exists to deny
    (Phase 18's T-18-CIPRIV comment warns against handing elevated tokens to PR-triggered runs).
    It runs on **push-to-`main` only**.
  Bolting the elevated job into the PR-triggered workflow would mean guarding it with
  `if: github.event_name == 'push' && github.ref == 'refs/heads/main'` and trusting nobody removes
  the guard — a structural-safety regression this project has consistently refused to make.
  **Accepted cost:** the site builds twice (once to gate, once to deploy). A few seconds; worth it.

- **D-04 (user-selected): dark, terminal-ish, in Dexter's voice.** Dark background, mono accents,
  lowercase copy, dry one-liners — **the page itself is a personality demo**, so a visitor feels the
  product before they reach the demo section. **Hard constraint:** the sarcasm lives in the *copy*,
  never in the *structure* — the page must stay legible, navigable, and professional. Personality
  rules apply (lowercase, one emoji max, dry).
  *(Rejected: clean/neutral SaaS styling — a beige page actively hides the one thing being
  demonstrated. Rejected: Discord-native blurple styling — reads as derivative, and edges toward
  implying an affiliation with Discord.)*

- **D-05 (user-selected): single scroll — hero → demo → features → honest boundaries → CTA.**
  The demo lands **high**, before the feature list (show, then tell). PORT-04's boundaries get a
  **real section**, not a footnote — and it sits **immediately before the closing CTA**, so a visitor
  reads "this bot is offline unless the owner is running it" **before** clicking Add-to-Discord, not
  after being disappointed. The Add-to-Discord button appears **twice** (hero + closing CTA).
  **Deep architecture detail is deliberately NOT on the page** — it links to the README case study
  (PORT-03), so there are never two copies of the architecture story to drift apart.
  *(Rejected: an on-page architecture section — duplicates PORT-03 on a second surface. Rejected:
  a multi-page site — over-built; more places for the invite link and disclosures to fall out of
  sync.)*

### The demo (PORT-02) — reinterpreted, and why

- **D-06 (user-selected, OVERRIDING Claude's recommendation, and REVERSING an earlier in-session
  decision): the demo is a styled HTML/CSS mock of a Discord conversation — NOT a screen recording —
  built from VERBATIM REAL Dexter output.**

  **The honesty rule that makes this legitimate, and which is NOT optional:** the transcript text
  **must be actual, unedited Dexter output**. A stylized HTML reproduction of a UI is a normal,
  honest convention (docs sites do it constantly) — what would make it dishonest is if *we wrote the
  roast lines ourselves*, because then the "personality demo" showcases our copywriting while
  implying it is Gemini's generation. **Real words, reconstructed pixels.** The page must never
  claim or imply it is a screen recording.

  **Why this won over a real recording:** it removes the phase's only human-blocking dependency
  entirely. The bot runs on the user's PC on demand, so a real capture needs a live session, a good
  take, and a screen recorder. The mock needs none of that — and because it is HTML, **Claude can
  render the README's GIF from it directly with Playwright**, end-to-end, with no capture session at
  all. The user's own argument, adopted: the landing page already carries a CTA inviting people to
  try the bot themselves, so the demo's job is to *convey the personality*, not to serve as forensic
  proof of function.

  **The two costs, stated plainly and to be disclosed, not hidden:**
  1. **PORT-02 literally says "demo GIF"** and means a recording of the running bot. The mock
     satisfies its **intent** (show the personality landing) but not its **letter**. This is a
     deliberate, recorded reinterpretation. The README GIF (D-07) happens to satisfy the literal
     "GIF" wording as a side effect, but the *provenance* is a mock, and that must not be obscured.
  2. **The mock cannot convincingly show the now-playing embed with its five control buttons** — the
     Phase 7 player UI. That is real product surface the demo will skip. The feature list and README
     must carry that weight instead.

  **Sourcing the verbatim lines — a lead for the researcher:** `logs/dexter.log` may already contain
  real generated Dexter responses from past sessions. **The researcher should check this first.** If
  it does, even the "user pastes a few real lines" step disappears and the phase becomes fully
  self-contained. If it does not, the user supplies a handful of real lines — a ~1-minute task, not
  a recording session — and that becomes the single item in `23-HUMAN-UAT.md` for PORT-02.

  *(Rejected: a real `.webm` recording + committed placeholder + HUMAN-UAT swap — this was
  **decided first and then reversed** by the user mid-discussion. It had the highest fidelity and
  showed the real player UI, but it blocked PORT-02 on a live session. Rejected earlier still: a raw
  `.gif` recording — multi-megabyte binary, worse quality, slower page. Rejected: "mock now, real
  recording later" — two demo implementations, and the "later" swap realistically never happens.)*

- **D-07 (user-selected): the README gets its own small `.gif`, rendered from the D-06 mock.**
  GitHub's markdown renderer does **not** reliably autoplay a relative `<video>` tag, so the landing
  page's animated mock cannot simply be reused in the README. Claude renders the mock with Playwright
  and emits a downscaled, lower-frame-rate `.gif` for the README. **One source, two derivatives** —
  no second authoring pass, and no chance of the two demos telling different stories.
  *(Rejected: a static screenshot linking to the site — a still can't show the timing of a joke,
  which is most of what makes the personality work. Rejected: no README demo at all — the single
  most persuasive artifact would be one click away from the surface most engineers land on first.)*

### README as case study (PORT-03)

- **D-08 (user-selected): mid-depth.** Tagline → badges → demo GIF → feature list → a **mermaid
  diagram of the cog → service → logic layering** → **3–4 "hard problem" callouts** (2–3 sentences
  each) → honest boundaries → invite link. Candidate callouts (planner picks the strongest 3–4):
  the pgvector RAG memory on **zero new infra**; the `_play_generation` counter that kills stale
  playback after-callbacks; the **accuracy firewall** (memory supplies the *episode*, live SQL
  supplies the *number*); the **two-choke-point** kill-switch enforcement. This is what a senior
  engineer skims in 90 seconds and comes away impressed by.
  *(Rejected: a deep per-subsystem case study — nobody reads a 900-line README and the good parts get
  buried. Rejected: a shallow product README — fails PORT-03's explicit "rewritten as an architecture
  case study" ask.)*

- **D-09 (user-selected): professional engineering prose, with Dexter quoted.** The case study is
  written **as the engineer** — clear, technical, **no sarcasm in the analysis**. Dexter's voice
  appears **only where he is the subject**: the demo, quoted example outputs, possibly the tagline.
  A recruiter needs to see that the author can write an architecture doc; a README that roasts the
  reader shows a bit and costs a lot. The landing page (D-04) already carries the personality.
  **Corollary:** PORT-04's disclosure section must read as **disclosure**, not as a joke.
  *(Rejected: fully in-persona — makes the engineering hard to evaluate on the one document where a
  hiring engineer wants signal about judgment. Rejected: zero personality anywhere — the README of a
  personality bot would never show the personality.)*

- **D-15 (user-selected): five badges — CI status, Python, discord.py, Postgres/pgvector, Gemini.**
  The **CI badge is required by PORT-03 and must point at the real workflow run** (which only exists
  after D-13's push). The other four are shields.io tech-stack badges naming the things that actually
  define the system. Five reads as considered; twelve reads as padding.
  **Explicitly excluded: a license badge** — it would imply a `LICENSE` file that does not exist, and
  adding one is not in this phase's scope.
  *(Rejected: CI-only — fails PORT-03's explicit "tech-stack badges". Rejected: the full 8-badge set
  incl. license + GHCR pull badge — badge soup is a known tell of an over-eager README.)*

### Honest disclosure (PORT-04)

- **D-10 (user-selected): both surfaces, framed as engineering tradeoffs.** A real section on the
  **landing page** (positioned per D-05, before the closing CTA) **and** a fuller version in the
  **README**. Each of the four boundaries states **the constraint, then the deliberate decision made
  in response** — e.g. *"full-savage personality in every server, mitigated by a reactive owner
  kill-switch, because a per-guild tone dial was over-engineering at this scale."*
  **Disclosure that reads as judgment, not as apology.**
  The four boundaries, with their actual shipped substance:
  1. **100-guild verification wall** — Discord bot verification is out of scope (REQUIREMENTS.md);
     the scale target is modest and this is documented rather than hidden.
  2. **On-demand hosting** — the bot is **offline unless the owner is running it** (the YouTube
     datacenter-IP block killed the free-cloud deploy; it runs on a residential PC → Neon).
     This one has a **user-facing consequence**, which is why D-05 puts it before the CTA.
  3. **Full-savage personality + reactive kill-switch** — the Phase 20 control plane
     (`/guilds list|silence|leave|block`, two choke points, persistent blocklist) is what makes this
     sentence defensible. Disclose the tradeoff, name the mitigation.
  4. **Hybrid memory scoping (as Phase 21 actually shipped)** — guild-scoped recall on
     `/roast @user` + ambient + proactive surfaces; `/ask` stays global (self-recall, no cross-user
     leak possible); the legacy `guild_id IS NULL` corpus is grandfathered as globally recallable;
     guild data is purged on removal. **Read `.planning/PROJECT.md` §Key Decisions for the shipped
     wording — do not describe the hypothesis, describe what shipped.**
  *(Rejected: README-only — someone clicks Add-to-Discord from the page, invites a bot that's offline
  most of the time, and finds out afterward: the exact bad experience PORT-04 exists to prevent.
  Rejected: a plain limitations list without the tradeoff framing — totally honest but reads as a
  list of things wrong with the project rather than evidence of deliberate judgment.)*

### CI/CD (CICD-02, CICD-03)

- **D-11 (user-selected): Pages publishes via `actions/deploy-pages` with an artifact.**
  build → `upload-pages-artifact` → `deploy-pages`, with `pages: write` + `id-token: write` scoped to
  that one job and a `github-pages` environment. **No build output is ever committed** — `dist/` stays
  a pure artifact.
  *(Rejected: pushing built output to a `gh-pages` branch — a second branch carrying generated files,
  a broader `contents: write` token, and a junk commit on every deploy.)*

- **D-12 (user-selected): the Pages deploy is GATED on the CI gate being green.** A merge to `main`
  that breaks the drift guard or the test suite **must not publish a landing page carrying a wrong
  invite URL** — that is the entire reason the D-02 scan exists. Implementation is planner's call
  (`workflow_run` keyed on `ci.yml` completing successfully on `main`, vs a `needs:`-dependent job) —
  but the **gate must be real**, not advisory.

- **D-16 (user-selected): GHCR publishes on a `v*` git tag, built multi-arch for `linux/amd64` +
  `linux/arm64`.** Tagging `v1.4.0` publishes `ghcr.io/jadrianports/dexter:v1.4.0` + `:latest`.
  **Multi-arch is load-bearing, not gold-plating:** the parked always-on host is most plausibly a
  Raspberry Pi (arm64), so an amd64-only image would be unpullable on the exact machine CICD-03
  exists to serve. Built via `docker/setup-buildx-action` + QEMU; costs a few extra minutes on a rare
  event. Needs `packages: write` — therefore its **own workflow file** (a third one), never `ci.yml`.
  *(Rejected: amd64-only — breaks the "zero build step" promise on the most likely target. Rejected:
  keying on a published GitHub Release — tidier, but this repo tags milestones (v1.0–v1.3) without
  cutting Releases, so it would be a new habit that may not stick.)*

- **D-17 (user-selected): the GHCR package is flipped PUBLIC by hand, recorded as a HUMAN-UAT item.**
  GHCR packages are **private by default** and visibility is a GitHub UI setting on the package page —
  it genuinely **cannot** be set from the publishing workflow on first push. So the workflow ships
  correct, and `23-HUMAN-UAT.md` carries one step: flip `dexter` to public, then verify
  `docker pull ghcr.io/jadrianports/dexter:v1.4.0` succeeds **from a logged-out shell**. Same
  acknowledged-deferred pattern as Phase 22's Dev Portal step (D-08).
  *(Rejected: leaving it private and documenting `docker login` — directly contradicts CICD-03's
  stated point, and a recruiter who tries the pull command hits an auth wall.)*

### Sequencing — the hard prerequisite

- **D-13 (user-selected): the 143-commit push is the FIRST TASK of the phase, before any Phase 23
  code is written.** This is a **hard blocker**, not bookkeeping.

  > **CORRECTION (2026-07-14, same session).** An earlier draft of this decision claimed *"`ci.yml`
  > has never actually executed."* **That was false** — Claude inferred it from the unpushed-commit
  > count without checking the run history, and the user challenged it. **Verified via
  > `gh run list`: CI has run three times (2026-07-09/10), one failure, then green.** The failure was
  > the unrelated import-time-exit bug, fixed by `e99a678`/`be0da7d`, and recorded green by
  > `efb4b60` (*"test(18): record CI gate UAT result (green on main)"*). The decision below stands,
  > but on the corrected, weaker premise.

  **The actual situation:** the repo (`github.com/jadrianports/dexter`, already **PUBLIC**) has
  `origin/main` parked at **Phase 18's tip (2026-07-10)**. The **143 unpushed commits are Phases 19,
  20, 21, and 22** — none of which CI has ever seen. The gate exists and is **proven working**; it
  simply has not been run against four phases of subsequent work, **including Phase 21's surgery on
  the memory subsystem** (the `search_memories` / `recall()` path that produced the Phase 13 CR-01
  blocker) and Phase 22's new drift-guard test.
  **Therefore:** push first, watch the run, and fix whatever breaks (a Ruff rule, the pgvector
  service container, a live-DB test that only passes locally) **while it is an isolated failure** —
  not tangled with a brand-new Astro build job, a Pages deploy, and a GHCR publish. Everything
  downstream in this phase (the CI badge, Pages, GHCR) depends on a **known-green baseline at HEAD**,
  and today's green badge would be reporting on Phase 18, not on the code being promoted.
  **The planner must still sequence a CI-repair contingency** — four unexercised phases through a
  gate is a realistic red, not a hypothetical.

  **Struck, on the corrected evidence:** `ci.yml`'s Pitfall-7 comment warns the native
  `davey`/PyNaCl install may fail on the first real run. **It did not** — the install worked on the
  GitHub runner. That risk is **retired**; do not plan around it, and consider removing the stale
  comment.

  *(Rejected: pushing at the end with the phase's work included — if CI is red for a Phase 19–22
  reason, it is discovered entangled with three new workflow jobs, and bisecting that is the worst
  possible way to find out.)*

- **D-14 (user-selected): the landing page lives at the default `jadrianports.github.io/dexter`.**
  Zero cost, zero DNS. **Pages footgun the researcher must lock down:** a project-page subpath
  requires Astro's `base: '/dexter'` config (and correct `site:`), or every asset path resolves
  wrong. This is a classic, well-documented failure — verify it explicitly.
  *(Rejected: a custom domain — sharper for a portfolio, but needs a domain, a CNAME + DNS records,
  and propagation, none of which an agent can verify. A distraction from shipping.)*

### Claude's / Planner's Discretion (do NOT re-ask the user)

- **How the D-02 `dist/` scan is invoked** — a pytest that shells out to the built directory and
  skips when absent, vs a standalone script step in `ci.yml`. Constraint: it **must fail the build on
  drift** and **must never silently skip in CI** (a silent skip recreates the vacuous-pass hole D-02
  exists to close). A **positive-control test** (the scanner provably finds a URL when one exists) is
  **required**, mirroring Phase 22 D-10's discipline.
- **Whether the existing `tests/test_invite_drift_guard.py` is extended or a sibling check is added** —
  the existing test's `.planning/`-exclusion and extension-allowlist logic is reusable; do not
  duplicate the regex.
- **The exact Astro project layout** (`site/src/pages/index.astro`, component split, where the mock
  transcript markup lives), `package.json` scripts, and Node version pinning in CI.
- **The mock demo's animation mechanism** (CSS keyframes vs a small scroll/reveal) and whether it
  honors `prefers-reduced-motion` — it **should**.
- **The Playwright render pipeline for the README GIF** (D-07) — resolution, frame rate, duration,
  and whether it lives in `scripts/`. Target: a small file (~1–2MB), crisp text.
- **Exact mermaid diagram content** for the README layering summary, and which 3–4 hard-problem
  callouts make the cut (D-08 lists four candidates).
- **Exact copy** for the landing page, the hero tagline, and the disclosure section — subject to
  D-04 (page: in-persona, lowercase, dry) and D-09 (README: professional, Dexter quoted only).
- **Workflow file names and job granularity** — `pages.yml` and a GHCR workflow (`release.yml` or
  similar) are the two new files implied by D-03/D-16; the exact names are the planner's.
- **GHCR image tag set** beyond `:v*` + `:latest` (e.g. a `:sha` tag) — planner's call.
- **How the CI-repair contingency (D-13) is structured** — a dedicated first plan, or a gating task
  inside plan 01.

### Reviewed Todos
None — `todo.match-phase 23` returned zero matches.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements (this phase)
- `.planning/ROADMAP.md` §"Phase 23: Portfolio Surface & CI/CD" — goal, the 5 success criteria, and
  the dependency chain (Phase 18 CI workflow to extend, Phase 19 `/setup` walkthrough proving the
  claims, Phase 20 kill-switch as the disclosed mitigation, Phase 22 working invite link).
  **SC-5 names the four PORT-04 boundaries verbatim.**
- `.planning/REQUIREMENTS.md` §"Portfolio Surface (PORT)" — PORT-01…04 verbatim. §"CI/CD (CICD)" —
  CICD-01 (**done**, Phase 18), CICD-02, CICD-03 verbatim.
- `.planning/REQUIREMENTS.md` §"Out of Scope" — **"Auto-deploy the bot to a live prod host"** and
  **"Discord bot verification / 100+ guild readiness"** (the latter is PORT-04 disclosure material,
  not a thing to build). §"Key Decisions (this milestone)" — the **hybrid memory scoping** row and
  the **full-savage + kill-switch** row, both of which PORT-04 discloses.
- `.planning/PROJECT.md` §"Key Decisions" — **the authoritative ledger of what actually shipped.**
  PORT-04 must describe the **shipped** memory-scoping decision, not the hypothesis. Also the parked
  24/7 deploy row (the on-demand hosting caveat) and the whole decision list that feeds D-08's
  hard-problem callouts.

### The Phase 22 invite contract (READ BEFORE TOUCHING ANY URL)
- `.planning/phases/22-invite-plumbing/22-CONTEXT.md` — **read D-03, D-07, D-10 in full.**
  `build_invite_url()` is the **ONLY** place an invite URL may be constructed; **no shorteners, no
  vanity redirects** (D-07); the guard **excludes `.planning/`** and uses a `.md`/`.html`/`.txt`
  extension allowlist (D-10). Its `<code_context>` §"Phase 23 hand-off" states the constraint
  directly: *"Phase 23 must NOT introduce a second URL constructor or a redirect."*
- `logic/invite.py::build_invite_url` — the single constructor. Locked bitfield `309240908864`
  (10 permissions, D-09 of Phase 22).
- `tests/test_invite_drift_guard.py` — the guard D-02 must keep real. Note its `.planning/` exclusion,
  its extension allowlist, and its **positive-control** test (proves the scanner finds a URL when one
  exists — the pattern D-02's `dist/` scan must replicate).
- `tests/test_invite_logic.py` / `tests/test_invite_cog.py` — the bitfield negative-assertion lock.
- `config.py` — `DISCORD_CLIENT_ID` (committed public constant + env override) and
  `INVITE_PERMISSIONS_VALUE`. **D-04 of Phase 22 exists precisely so CI, with no secrets, can build
  the URL** — that property is what makes D-02's CI scan possible at all.

### CI/CD (the workflow this phase extends)
- `.github/workflows/ci.yml` — the Phase 18 gate. **Read the header comments**: the deliberate
  `on: push / pull_request` (never `pull_request_target` — T-18-CIPRIV), the top-level
  `permissions: contents: read` least-privilege ceiling (**the constraint that forces D-03's split**),
  the `pgvector/pgvector:pg16` service container, `TEST_DATABASE_URL`, and **Pitfall 7** — the
  standing warning that the native `davey`/PyNaCl install may fail on the first real run (**D-13's
  whole point**).
- `Dockerfile` — `python:3.11-slim-bookworm` + ffmpeg. What CICD-03 publishes. Note its header:
  "multi-arch (amd64 on Koyeb/CI, arm64 on dev machines)" — **the multi-arch intent D-16 makes real**.
  Secrets are injected at runtime, never baked into layers (T-04-05) — the GHCR build must preserve
  that.
- `.planning/phases/18-per-guild-config-foundation-ci-gate/18-CONTEXT.md` — the CI gate's original
  decisions (incl. D-15, the `TEST_DATABASE_URL` service container that unskips ~107 live-DB tests).

### PORT-04 substance (what is actually being disclosed)
- `.planning/phases/20-owner-control-plane-rate-observability/20-CONTEXT.md` §`<specifics>` — the
  closing bullet says it outright: *"PORT-04's disclosure is being earned here."* The kill-switch's
  reality (D-01 blocklist table, D-11 block=leave+blacklist, D-13 two choke points) is what makes the
  "full-savage + reactive kill-switch" sentence defensible.
- `.planning/phases/21-memory-scoping-guild-data-lifecycle/21-CONTEXT.md` — the hybrid scoping
  decisions (D-01 grandfathered NULL corpus, D-02 read-path-only, D-03 purge). Its `<deferred>`
  section hands **"PORT-04 disclosure copy"** explicitly to this phase.
- `CLAUDE.md` §"Database Schema" + §"Critical Rules" 11–17 — the shipped memory-scoping narrative in
  its most current form (Critical Rule 17 states the guild-scoping opt-in rule exactly).

### Personality + copy constraints
- `CLAUDE.md` §"Critical Rules" 6–9 — dial back sarcasm for serious content (**the PORT-04 section is
  serious content**), one emoji max, lowercase, never sacrifice accuracy for personality. These govern
  the **landing page** copy (D-04) and the **quoted Dexter output** in the README (D-09) — but not the
  README's own analytical prose.
- `personality/prompts.py` / `personality/responses.py` — the canonical voice, if example copy is
  needed.

### Demo sourcing (D-06)
- `logs/dexter.log` — **researcher: check this FIRST.** It may already contain real generated Dexter
  responses from past sessions. If it does, the verbatim transcript for the mock can be sourced
  without any user action at all, and PORT-02 becomes fully self-contained.
- `cogs/ai.py` (`/roast`, `/ask`), `cogs/music.py` (`/play` responses), `cogs/events.py` (ambient
  roasts) — the surfaces whose real output the mock reproduces.

### Prior-phase HUMAN-UAT precedent
- `.planning/phases/22-invite-plumbing/22-HUMAN-UAT.md` — the acknowledged-deferred pattern D-17
  (GHCR public flip) and any residual PORT-02 item follow. Every phase since 11 uses it.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`logic/invite.py::build_invite_url()`** — the single URL constructor. The landing page's
  Add-to-Discord button (×2, D-05) and the README's invite link both resolve to its output, and D-02's
  `dist/` scan asserts it.
- **`tests/test_invite_drift_guard.py`** — its regex, its `.planning/` directory exclusion, and its
  **positive-control** fixture are all directly reusable by D-02's `dist/` scan. Extend; do not
  duplicate the regex.
- **`.github/workflows/ci.yml`** — the gate D-02's scan job joins. Its structure (checkout →
  setup-python → pip install → ruff → pytest) is the template; the new site job adds
  `actions/setup-node` → `npm ci` → `npm run build` → scan.
- **`Dockerfile`** — already written and multi-arch-intended; CICD-03 publishes it unchanged.
- **`config.py::DISCORD_CLIENT_ID` / `INVITE_PERMISSIONS_VALUE`** — public, committed, **readable in
  CI with no secrets**. This is what makes a CI-side URL assertion possible.

### Established Patterns
- **Structural safety over remembered safety** (Phase 18 D-01, Phase 20 OWNER-05) — the reason D-02
  guards the built artifact and D-03 refuses to put an elevated job behind an `if:` guard.
- **Least-privilege CI** (`permissions: contents: read`; never `pull_request_target`) — D-03's split
  exists to preserve this.
- **No silent caps / no silent skips** (Phase 19 D-15, Phase 20 D-10) — D-02's scan **must not
  silently skip in CI**; a vacuous pass is the failure mode being designed against.
- **Additive, honest disclosure over hidden limitation** — the milestone's stated posture
  (REQUIREMENTS.md Out-of-Scope table repeatedly says "documented as an honest boundary in PORT-04").
- **Acknowledged-deferred HUMAN-UAT items** for anything an agent genuinely cannot do (Phase 11
  onward) — D-17's GHCR public flip, and any residual PORT-02 line-sourcing.

### Integration Points
- **`/site/`** — new directory. Astro project (`package.json`, `astro.config.mjs` with
  `base: '/dexter'`, `src/pages/index.astro`, `src/assets/`).
- **`.github/workflows/ci.yml`** — new site-build + drift-scan job (unprivileged).
- **`.github/workflows/pages.yml`** — NEW. Privileged Pages deploy, main-only, gated on CI (D-12).
- **`.github/workflows/<release>.yml`** — NEW. GHCR multi-arch publish on `v*` tags (`packages: write`).
- **`README.md`** — full rewrite (currently **2 lines**).
- **`docs/demo.gif`** (or similar) — the Playwright-rendered README asset (D-07).
- **`scripts/`** — the Playwright render pipeline for D-07.
- **`23-HUMAN-UAT.md`** — D-17's GHCR public flip; PORT-02's line-sourcing if `logs/` doesn't supply it.
- **Regression surface:** the invite drift guard. Any change to how the URL reaches a doc must keep
  `tests/test_invite_drift_guard.py` green **and non-vacuous**.

</code_context>

<specifics>
## Specific Ideas

- **The drift guard is the one thing that can silently rot in this phase.** Choosing an SSG (D-01)
  broke Phase 22's guarantee by construction, and D-02 is the repair. The failure mode is not a red
  build — it is a **green build that guards nothing**. Every implementation choice around D-02 should
  be evaluated against one question: *"if the URL in the shipped page were wrong, would this fail?"*
  The positive-control test is not optional.

- **The demo's honesty rests entirely on the words being real.** D-06's mock is legitimate **because
  and only because** the transcript is verbatim Dexter output. If an executor "improves" a roast line
  for punchiness, the demo becomes a fabrication on a page whose thesis is honest disclosure. Source
  the lines from `logs/dexter.log` or from the user — **never write them.**

- **PORT-04 is the page's spine, not its apology.** The four boundaries are framed as
  constraint → deliberate decision (D-10). The hosting caveat in particular has a real user-facing
  consequence, which is why it sits *before* the CTA (D-05) — a visitor should never invite a bot
  that's usually offline without having been told.

- **The push is the phase's true first task.** Everything recruiter-facing here (a badge that reflects
  a real run, a live Pages URL, a pullable image) is a claim about GitHub — and GitHub's `main` is
  still parked at Phase 18. A CI badge today would be truthfully reporting on code four phases old.
  A red run when Phases 19–22 finally land is a realistic outcome; D-13 sequences it where it is cheap
  to fix. (See D-13's correction block — an earlier draft overstated this as "CI has never run.")

- **Two surfaces, one story, zero duplication.** The landing page shows and links; the README explains.
  Architecture detail lives in exactly one place (D-05). The invite URL is generated in exactly one
  place (Phase 22 D-03). The demo is authored once and derived twice (D-07). Every duplication this
  phase avoids is a drift it cannot suffer.

</specifics>

<deferred>
## Deferred Ideas

- **A real screen-recorded demo of the running bot** (`.webm` of `/roast` → `/play` → `/ask`, showing
  the Phase 7 now-playing embed + control buttons) — **rejected for this phase in favor of D-06's
  mock**, which unblocks PORT-02 entirely. If a live session ever produces a good take, it is a
  drop-in upgrade to the landing page's demo section. Noted honestly: "later" swaps often never happen.
- **A `LICENSE` file + license badge** — excluded from D-15 because the badge would imply a file that
  does not exist. Adding one is a separate, trivial decision, not Phase 23's.
- **A custom domain for the landing page** — rejected in D-14; needs a domain, DNS, and propagation
  that no agent can verify.
- **A prod auto-deploy of the bot** — permanently Out of Scope this milestone (there is no prod host).
  CICD-03 makes a future host a `docker pull` away; that is the whole extent of it.
- **Runtime permission-gap self-diagnostic (`/permcheck`)** — carried over from Phase 22's deferred
  list; still a genuine new capability, still not this phase.
- **A vanity/short invite link** — ruled out by Phase 22 D-07; it defeats the literal-match drift
  guard. Would require redesigning the guard first.

### Reviewed Todos (not folded)
None — `todo.match-phase 23` returned zero matches.

</deferred>

---

*Phase: 23-portfolio-surface-ci-cd*
*Context gathered: 2026-07-14*
